import geo_lib

import logging
import logger_tools
import phonenumbers
import motlin_lib
import os
import redis_lib

from datetime import datetime
from dotenv import load_dotenv

from telegram import LabeledPrice
from telegram.ext import Filters, Updater
from telegram.ext import PreCheckoutQueryHandler
from telegram.ext import CallbackQueryHandler, MessageHandler, CommandHandler
from tg_bot_events import add_product_to_cart, choose_payment_type
from tg_bot_events import confirm_deliviry, find_nearest_address, finish_order
from tg_bot_events import save_customer_phone, save_customer_address
from tg_bot_events import show_store_menu, show_product_card, show_products_in_cart
from tg_bot_events import show_delivery_messages, show_reminder


logger = logging.getLogger('pizza_delivery_bot')


class TgDialogBot(object):

    def __init__(self, tg_token, states_functions, **params):
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
        self.updater.start_polling()

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
            bot,
            chat_id,
            motlin_token,
            query.data,
            query.message.message_id
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
        bot.send_message(chat_id=chat_id, text='Пришлите, пожалуйста, Ваш номер телефона')
        if query.message.message_id:
            bot.delete_message(chat_id=chat_id, message_id=query.message.message_id)
        return 'WAITING_PHONE'
    else:
        motlin_lib.delete_from_cart(motlin_token, chat_id, query.data)
        show_products_in_cart(bot, chat_id, motlin_token, query.message.message_id)
        return 'HANDLE_CART'


def waiting_phone(bot, update, motlin_token, params):
    if update.message.text and phonenumbers.is_valid_number(phonenumbers.parse(update.message.text, 'RU')):
        save_customer_phone(bot, str(update.message.chat_id), motlin_token, update.message.text, update.message.message_id)
        return 'HANDLE_WAITING'
    else:
        bot.send_message(chat_id=update.message.chat_id, text='Вы ввели не корректный номер телефона. Поробуйте еще раз:')
        if update.message.message_id:
            bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)
        return 'WAITING_PHONE'


def handle_waiting(bot, update, motlin_token, params):
    query = update.callback_query
    if query and query.data == 'HANDLE_MENU':
        finish_order(bot, query.message.chat_id, query.message.message_id)
        return query.data
    elif query and query.data == 'HANDLE_WAITING':
        bot.send_message(chat_id=query.message.chat_id, text='Пришлите, пожалуйста, Ваш адрес или геолокацию')
        return query.data
    else:
        longitude, latitude = None, None
        if update.message.text:
            longitude, latitude = geo_lib.fetch_coordinates(params['ya_api_key'], update.message.text)
            customer_address = update.message.text
        elif update.message.location:
            longitude, latitude = update.message.location.longitude, update.message.location.latitude
            customer_address = geo_lib.fetch_address(params['ya_api_key'], longitude, latitude)
        if not longitude == latitude is None:
            chat_id = update.message.chat_id
            nearest_address = find_nearest_address(motlin_token, longitude, latitude)
            params['redis_conn'].add_value(chat_id, 'nearest_pizzeria', nearest_address['address'])
            confirm_deliviry(bot, chat_id, motlin_token, nearest_address)
            save_customer_address(bot, str(chat_id), motlin_token, customer_address, longitude, latitude)
        else:
            bot.send_message(chat_id=update.message.chat_id, text='Вы ввели не корректную геопозицию. Поробуйте еще раз:')
        return 'HANDLE_DELIVERY'


def handle_delivery(bot, update, motlin_token, params):
    query = update.callback_query
    chat_id = query.message.chat_id
    pizzeria_address = motlin_lib.get_address(
        motlin_token,
        'pizzeria',
        'address',
        params['redis_conn'].get_value(chat_id, 'nearest_pizzeria')
    )
    if query.data == 'HANDLE_DELIVERY':
        customer_address = motlin_lib.get_address(motlin_token, 'customeraddress', 'customerid', str(chat_id))
        if pizzeria_address and customer_address:
            show_delivery_messages(
                bot,
                chat_id,
                pizzeria_address['telegramid'],
                motlin_token,
                customer_address['latitude'],
                customer_address['longitude']
            )
        params['job'].run_once(show_reminder, 3600, context=chat_id)
    else:
        if pizzeria_address:
            bot.send_location(chat_id=chat_id, latitude=pizzeria_address['latitude'], longitude=pizzeria_address['longitude'])
        message = f'Вы сможете забрать пиццу по адресу: {pizzeria_address["address"]}'
        bot.send_message(chat_id=chat_id, text=message)
    choose_payment_type(bot, chat_id)
    return 'HANDLE_PAYMENT'


def handle_payment(bot, update, motlin_token, params):
    if update.message and update.message.successful_payment:
        finish_order(bot, update.message.chat_id)
        return 'HANDLE_MENU'
    else:
        query = update.callback_query
        chat_id = query.message.chat_id
        if query.data == 'FINISH_ORDER':
            finish_order(bot, chat_id, True, query.message.message_id)
            return 'HANDLE_MENU'
        else:
            description, currency, price = motlin_lib.get_payment_info(motlin_token, chat_id)
            bot.send_invoice(
                chat_id,
                'Оплата заказа',
                description,
                'Tranzzo payment',
                params['payment_token'],
                'payment',
                currency,
                [LabeledPrice('Заказ', price * 100)]
            )
            bot.delete_message(chat_id=chat_id, message_id=query.message.message_id)
            return 'PAYMENT_WAITING'


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
            payment_token=os.getenv('PAYMENT_TOKEN')
        )
        bot.start()
    except Exception as error:
        logger.exception(f'Ошибка бота: {error}')
        launch_store_bot(states_functions)


def main():
    load_dotenv()

    logger_tools.initialize_logger(
        logger,
        os.getenv('TG_LOG_TOKEN'),
        os.getenv('TG_CHAT_ID')
    )

    states_functions = {
        'START': start,
        'HANDLE_MENU': handle_menu,
        'HANDLE_DESCRIPTION': handle_description,
        'HANDLE_CART': handle_cart,
        'WAITING_PHONE': waiting_phone,
        'HANDLE_WAITING': handle_waiting,
        'HANDLE_DELIVERY': handle_delivery,
        'HANDLE_PAYMENT': handle_payment,
        'PAYMENT_WAITING': payment_waiting
    }

    launch_store_bot(states_functions)


if __name__ == '__main__':
    main()
