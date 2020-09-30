import logging
import phonenumbers
import os
from datetime import datetime
from dotenv import load_dotenv

from libs import geo_lib
from libs import logger_lib
from libs import motlin_lib
from libs import redis_lib

from telegram import LabeledPrice
from telegram.ext import Filters, Updater
from telegram.ext import PreCheckoutQueryHandler
from telegram.ext import CallbackQueryHandler, MessageHandler, CommandHandler
from tg_bot_events import add_product_to_cart, choose_payment_type
from tg_bot_events import clear_settings_and_task_queue, get_delivery_time
from tg_bot_events import delete_messages, choose_deliviry, confirm_deliviry
from tg_bot_events import confirm_order, find_nearest_address, send_courier_message
from tg_bot_events import save_customer_phone, save_customer_email, save_customer_address
from tg_bot_events import show_store_menu, show_product_card, show_products_in_cart
from tg_bot_events import show_reminder, show_customers_menu, send_or_update_courier_messages

from validate_email import validate_email

logger = logging.getLogger('pizza_delivery_bot')

CLIENT_REMINDER_PERIOD = 3600
COURIER_REMINDER_PERIOD = 60
PORT = os.getenv('PORT')


class TgDialogBot(object):

    def __init__(self, tg_token, states_functions, **params):
        self.tg_token = tg_token
        self.params = params
        self.updater = Updater(token=tg_token)
        self.updater.dispatcher.add_handler(CallbackQueryHandler(self.handle_users_reply))
        self.updater.dispatcher.add_handler(MessageHandler(Filters.successful_payment, self.handle_users_reply))
        self.updater.dispatcher.add_handler(MessageHandler(Filters.text, self.handle_users_reply))
        self.updater.dispatcher.add_handler(MessageHandler(Filters.location, self.handle_geodata))
        self.updater.dispatcher.add_handler(CommandHandler('start', self.handle_users_reply))
        self.updater.dispatcher.add_handler(PreCheckoutQueryHandler(self.handle_users_reply))
        self.updater.dispatcher.add_error_handler(self.error)
        self.states_functions = states_functions
        self.motlin_token, self.token_expires = None, 0
        self.params['job'] = self.updater.job_queue

    def start(self):
        self.updater.start_webhook(listen="0.0.0.0", port=int(PORT), url_path=self.tg_token)
        self.updater.bot.setWebhook(self.params['heroku_url'] + self.tg_token)
        self.updater.idle()

    def handle_geodata(self, bot, update):
        next_state = self.states_functions['HANDLE_WAITING'](bot, update, self.motlin_token, self.params)
        self.params['redis_conn'].add_value(update.message.chat_id, 'state', next_state)

    def update_motlin_token(self):
        if self.token_expires < datetime.now().timestamp():
            self.motlin_token, self.token_expires = motlin_lib.get_moltin_access_token(
                client_secret=self.params['motlin_client_secret'],
                client_id=self.params['motlin_client_id']
            )

    def handle_users_reply(self, bot, update):
        self.update_motlin_token()
        if update.message:
            user_reply = update.message.text
            chat_id = update.message.chat_id
        elif update.callback_query:
            user_reply = update.callback_query.data
            chat_id = update.callback_query.message.chat_id
        elif update.pre_checkout_query:
            user_reply = ''
            chat_id = update.pre_checkout_query.from_user.id
        else:
            return

        if user_reply == '/start':
            user_state = 'START'
        else:
            user_state = self.params['redis_conn'].get_value(chat_id, 'state')

        state_handler = self.states_functions[user_state]
        next_state = state_handler(bot, update, self.motlin_token, self.params)
        self.params['redis_conn'].add_value(chat_id, 'state', next_state)

    def error(self, bot, update, error):
        logger.exception(f'Ошибка бота: {error}')


def start(bot, update, motlin_token, params):
    if motlin_lib.get_address(motlin_token, 'pizzeria', 'telegramid', update.message.chat_id):
        clear_settings_and_task_queue(update.message.chat_id, params)
        bot.send_message(chat_id=update.message.chat_id, text='Добро пожаловать! Ожидайте заказы на доставку!')
        return 'HANDLE_DELIVERY'
    else:
        current_page = params['redis_conn'].get_value(update.message.chat_id, 'current_page')
        show_store_menu(bot, update.message.chat_id, motlin_token, page=current_page)
        return 'HANDLE_MENU'


def handle_menu(bot, update, motlin_token, params):
    query = update.callback_query
    chat_id = query.message.chat_id
    if query.data == str(chat_id):
        show_products_in_cart(bot, chat_id, motlin_token, query.message.message_id)
        return 'HANDLE_CART'
    elif query.data.isdecimal():
        params['redis_conn'].add_value(chat_id, 'current_page', query.data)
        show_store_menu(bot, chat_id, motlin_token, query.message.message_id, query.data)
        return 'HANDLE_MENU'
    else:
        show_product_card(
            bot, chat_id, motlin_token,
            query.data, query.message.message_id
        )
        return 'HANDLE_DESCRIPTION'


def handle_description(bot, update, motlin_token, params):
    query = update.callback_query
    chat_id = query.message.chat_id
    if query.data == 'HANDLE_MENU':
        current_page = params['redis_conn'].get_value(chat_id, 'current_page')
        show_store_menu(bot, chat_id, motlin_token, query.message.message_id, current_page)
        return query.data
    elif query.data == str(chat_id):
        show_products_in_cart(bot, chat_id, motlin_token, query.message.message_id)
        return 'HANDLE_CART'
    else:
        add_product_to_cart(chat_id, motlin_token, query.data, query)
        return 'HANDLE_DESCRIPTION'


def handle_cart(bot, update, motlin_token, params):
    query = update.callback_query
    chat_id = query.message.chat_id
    if query.data == 'HANDLE_MENU':
        current_page = params['redis_conn'].get_value(chat_id, 'current_page')
        show_store_menu(bot, chat_id, motlin_token, query.message.message_id, current_page)
        return query.data
    elif query.data == str(chat_id):
        show_customers_menu(bot, chat_id, motlin_token)
        delete_messages(bot, chat_id, query.message.message_id)
        return 'HANDLE_CUSTOMERS'
    else:
        motlin_lib.delete_from_cart(motlin_token, chat_id, query.data)
        show_products_in_cart(bot, chat_id, motlin_token, query.message.message_id)
        return 'HANDLE_CART'


def handle_customers(bot, update, motlin_token, redis_conn):
    query = update.callback_query
    chat_id = query.message.chat_id
    if query.data == 'CUSTOMERS_MAIL':
        bot.send_message(chat_id=chat_id, text='Ваш адрес электронной почты:')
        delete_messages(bot, chat_id, query.message.message_id)
        return 'WAITING_EMAIL'
    elif query.data == 'CUSTOMERS_PHONE':
        bot.send_message(chat_id=chat_id, text='Ваш контактный телефон:')
        delete_messages(bot, chat_id, query.message.message_id)
        return 'WAITING_PHONE'
    else:
        bot.send_message(chat_id=chat_id, text='Пришлите, пожалуйста, Ваш адрес или геолокацию')
        delete_messages(bot, chat_id, query.message.message_id)
        return 'HANDLE_WAITING'


def waiting_email(bot, update, motlin_token, redis_conn):
    chat_id = update.message.chat_id
    if update.message.text and validate_email(update.message.text):
        save_customer_email(bot, str(update.message.chat_id), motlin_token, update.message.text)
        if not motlin_lib.get_customer(motlin_token, 'email', update.message.text):
            motlin_lib.add_new_customer(motlin_token, update.message.text)
        show_customers_menu(bot, chat_id, motlin_token)
        delete_messages(bot, chat_id, update.message.message_id, 2)
        return 'HANDLE_CUSTOMERS'
    else:
        bot.send_message(chat_id=update.message.chat_id, text='Вы ввели не корректный email. Поробуйте еще раз:')
        return 'WAITING_EMAIL'


def waiting_phone(bot, update, motlin_token, params):
    chat_id = update.message.chat_id
    if update.message.text and phonenumbers.is_valid_number(phonenumbers.parse(update.message.text, 'RU')):
        save_customer_phone(bot, str(update.message.chat_id), motlin_token, update.message.text)
        show_customers_menu(bot, chat_id, motlin_token)
        delete_messages(bot, chat_id, update.message.message_id, 2)
        return 'HANDLE_CUSTOMERS'
    else:
        bot.send_message(chat_id=update.message.chat_id, text='Вы ввели не корректный номер телефона. Поробуйте еще раз:')
        delete_messages(bot, update.message.chat_id, update.message.message_id, message_numbers=2)
        return 'WAITING_PHONE'


def handle_waiting(bot, update, motlin_token, params):
    query = update.callback_query
    longitude, latitude = None, None
    if query and query.data == 'HANDLE_MENU':
        chat_id = query.message.chat_id
        order_id = confirm_order(bot, chat_id, query.message.message_id)
        params['redis_conn'].add_value(chat_id, 'order', order_id)
        return query.data
    elif query and query.data == 'HANDLE_WAITING':
        bot.send_message(chat_id=query.message.chat_id, text='Пришлите, пожалуйста, Ваш адрес или геолокацию')
        return query.data
    elif update.message.text:
        longitude, latitude = geo_lib.fetch_coordinates(params['ya_api_key'], update.message.text)
        customer_address = update.message.text
        delete_messages(bot, update.message.chat_id, update.message.message_id - 1)
    elif update.message.location:
        longitude, latitude = update.message.location.longitude, update.message.location.latitude
        customer_address = geo_lib.fetch_address(params['ya_api_key'], longitude, latitude)
        delete_messages(bot, update.message.chat_id, update.message.message_id - 1)

    if not longitude == latitude is None:
        chat_id = update.message.chat_id
        nearest_address = find_nearest_address(motlin_token, longitude, latitude)
        params['redis_conn'].add_value(chat_id, 'nearest_pizzeria', nearest_address['address'])
        choose_deliviry(bot, chat_id, motlin_token, nearest_address)
        save_customer_address(
            bot, str(chat_id), motlin_token, customer_address, longitude, latitude,
            geo_lib.fetch_address_decryption(params['ya_api_key'], longitude, latitude)
        )
        return 'HANDLE_DELIVERY'
    else:
        bot.send_message(chat_id=update.message.chat_id, text='Вы ввели не корректный адрес или геопозицию. Поробуйте еще раз:')
        return 'HANDLE_WAITING'


def handle_delivery(bot, update, motlin_token, params, customer_chat_id=''):
    if customer_chat_id:
        query, chat_id, message_id = None, int(customer_chat_id), None
    elif update.callback_query:
        query, chat_id = update.callback_query, update.callback_query.message.chat_id
        message_id = query.message.message_id
    elif update.message:
        query, chat_id, message_id = None, update.message.chat_id, 0

    pizzeria_address = motlin_lib.get_address(
        motlin_token, 'pizzeria', 'address',
        params['redis_conn'].get_value(chat_id, 'nearest_pizzeria')
    )
    delivery_type = params['redis_conn'].get_value(chat_id, 'delivery_type')
    delivery_price = params['redis_conn'].get_value(chat_id, 'delivery_price')
    pay_by_cash = bool(params['redis_conn'].get_value(chat_id, 'cash_payment'))

    if query and 'COURIER_DELIVERY' in query.data:
        delivery_price = query.data.replace('COURIER_DELIVERY', '')
        params['redis_conn'].add_value(chat_id, 'delivery_type', 'COURIER_DELIVERY')
        params['redis_conn'].add_value(chat_id, 'delivery_price', int(delivery_price if delivery_price else 0))
        params['job'].run_once(show_reminder, CLIENT_REMINDER_PERIOD, context=chat_id)
        delete_messages(bot, chat_id, message_id, message_numbers=2)
    elif query and pizzeria_address and query.data == 'PICKUP_DELIVERY':
        params['redis_conn'].add_value(chat_id, 'delivery_type', 'PICKUP_DELIVERY')
        bot.send_location(chat_id=chat_id, latitude=pizzeria_address['latitude'], longitude=pizzeria_address['longitude'])
        bot.send_message(
            chat_id=chat_id,
            text=f'Вы сможете забрать пиццу по адресу: {pizzeria_address["address"]}')
        delete_messages(bot, chat_id, message_id, message_numbers=2)
    elif pizzeria_address and delivery_type == 'COURIER_DELIVERY':
        courier_id = pizzeria_address['telegramid']
        params['job'].run_repeating(
            send_or_update_courier_messages,
            COURIER_REMINDER_PERIOD,
            first=0,
            context={
                'chat_id': chat_id,
                'courier_id': courier_id,
                'motlin_token': motlin_token,
                'customer_address': motlin_lib.get_address(
                    motlin_token, 'customeraddress',
                    'customerid', str(chat_id)
                ),
                'delivery_price': delivery_price,
                'cash': pay_by_cash,
                'redis_conn': params['redis_conn'],
                'delivery_time': get_delivery_time(params['redis_conn'], chat_id, CLIENT_REMINDER_PERIOD)
            }
        )
        params['redis_conn'].add_value(courier_id, 'state', 'UPDATE_HANDLER')
        return 'UPDATE_HANDLER'
    else:
        return 'HANDLE_DELIVERY'
    choose_payment_type(bot, chat_id)
    return 'HANDLE_PAYMENT'


def handle_payment(bot, update, motlin_token, params):
    if update.message and update.message.successful_payment:
        chat_id = update.message.chat_id
        order_id = confirm_order(bot, chat_id, motlin_token)
        params['redis_conn'].add_value(chat_id, 'order', order_id)
        delivery_type = params['redis_conn'].get_value(chat_id, 'delivery_type')
        if delivery_type == 'PICKUP_DELIVERY':
            motlin_lib.confirm_order_shipping(motlin_token, order_id)
            motlin_lib.delete_the_cart(motlin_token, chat_id)
            clear_settings_and_task_queue(chat_id, params)
        else:
            handle_delivery(bot, update, motlin_token, params)
        return 'UPDATE_HANDLER'
    elif update.callback_query and update.callback_query.data == 'CASH_PAYMENT':
        chat_id = update.callback_query.message.chat_id
        order_id = confirm_order(bot, chat_id, motlin_token, True, update.callback_query.message.message_id)
        params['redis_conn'].add_value(chat_id, 'order', order_id)
        params['redis_conn'].add_value(chat_id, 'cash_payment', 1)
        handle_delivery(bot, update, motlin_token, params)
        delivery_type = params['redis_conn'].get_value(chat_id, 'delivery_type')
        if delivery_type == 'PICKUP_DELIVERY':
            motlin_lib.confirm_order_shipping(motlin_token, order_id)
            motlin_lib.delete_the_cart(motlin_token, chat_id)
            clear_settings_and_task_queue(chat_id, params)
        return 'UPDATE_HANDLER'
    elif update.callback_query and update.callback_query.data == 'CARD_PAYMENT':
        chat_id = update.callback_query.message.chat_id
        params['redis_conn'].add_value(chat_id, 'cash_payment', 0)
        description, currency, price = motlin_lib.get_payment_info(motlin_token, chat_id)
        bot.send_invoice(
            chat_id, 'Оплата заказа',
            description, 'Tranzzo payment',
            params['payment_token'],
            'payment', currency,
            [LabeledPrice('Заказ', price * 100)]
        )
        delete_messages(bot, chat_id, update.callback_query.message.message_id)
        return 'PAYMENT_WAITING'
    else:
        return 'HANDLE_PAYMENT'


def payment_waiting(bot, update, motlin_token, params):
    query = update.pre_checkout_query
    if query.invoice_payload != 'Tranzzo payment':
        bot.answer_pre_checkout_query(
            pre_checkout_query_id=query.id,
            ok=False,
            error_message="Что то пошло не так..."
        )
    else:
        bot.answer_pre_checkout_query(pre_checkout_query_id=query.id, ok=True)
    return 'HANDLE_PAYMENT'


def update_handler(bot, update, motlin_token, params):
    query = update.callback_query
    chat_id = query.message.chat_id
    if 'DELIVEREDYES' in query.data:
        customer_chat_id = query.data.replace('DELIVEREDYES', '')
        motlin_lib.confirm_order_shipping(
            motlin_token,
            params['redis_conn'].get_value(customer_chat_id, 'order')
        )
        delete_messages(bot, chat_id, query.message.message_id)
        motlin_lib.delete_the_cart(motlin_token, customer_chat_id)
        clear_settings_and_task_queue(chat_id, params)
        clear_settings_and_task_queue(customer_chat_id, params)
        return 'UPDATE_HANDLER'
    elif 'DELIVEREDTO' in query.data:
        confirm_deliviry(
            bot, chat_id,
            query.data.replace('DELIVEREDTO', ''),
            query.message.message_id
        )
    else:
        send_courier_message(
            bot, [
                query.data, chat_id, motlin_token,
                motlin_lib.get_address(motlin_token, 'customeraddress', 'customerid', query.data),
                params['redis_conn'].get_value(query.data, 'delivery_price'),
                bool(params['redis_conn'].get_value(query.data, 'cash_payment')),
                params['redis_conn'],
                get_delivery_time(params['redis_conn'], query.data, CLIENT_REMINDER_PERIOD)
            ]
        )
        delete_messages(bot, chat_id, query.message.message_id)
    return 'UPDATE_HANDLER'


def launch_store_bot(states_functions):
    try:
        redis_conn = redis_lib.RedisDb(
            os.getenv('REDIS_HOST'),
            os.getenv('REDIS_PORT'),
            os.getenv('REDIS_PASSWORD')
        )
        bot = TgDialogBot(
            os.getenv('TG_ACCESS_TOKEN'),
            states_functions,
            redis_conn=redis_conn,
            motlin_client_id=os.getenv('MOLTIN_CLIENT_ID'),
            motlin_client_secret=os.getenv('MOLTIN_CLIENT_SECRET'),
            ya_api_key=os.getenv('YANDEX_API_KEY'),
            payment_token=os.getenv('PAYMENT_TOKEN'),
            heroku_url=os.getenv('HEROKU_URL')
        )
        bot.start()
    except Exception as error:
        logger.exception(f'Ошибка бота: {error}')
        launch_store_bot(states_functions)


def main():
    load_dotenv()

    logger_lib.initialize_logger(
        logger,
        os.getenv('TG_LOG_TOKEN'),
        os.getenv('TG_CHAT_ID')
    )

    states_functions = {
        'START': start,
        'HANDLE_MENU': handle_menu,
        'HANDLE_DESCRIPTION': handle_description,
        'HANDLE_CART': handle_cart,
        'HANDLE_CUSTOMERS': handle_customers,
        'WAITING_EMAIL': waiting_email,
        'WAITING_PHONE': waiting_phone,
        'HANDLE_WAITING': handle_waiting,
        'HANDLE_DELIVERY': handle_delivery,
        'HANDLE_PAYMENT': handle_payment,
        'PAYMENT_WAITING': payment_waiting,
        'UPDATE_HANDLER': update_handler
    }

    launch_store_bot(states_functions)


if __name__ == '__main__':
    main()
