import geo_lib

import logging
import logger_tools

import motlin_lib
import motlin_load
import os
import redis_lib

from datetime import datetime
from dotenv import load_dotenv

from telegram.ext import Filters, Updater
from telegram.ext import CallbackQueryHandler, MessageHandler, CommandHandler
from tg_bot_events import add_product_to_cart
from tg_bot_events import find_nearest_address, confirm_email, confirm_deliviry
from tg_bot_events import show_store_menu, show_product_card, show_delivery_messages
from tg_bot_events import show_products_in_cart, show_reminder, finish_order

from validate_email import validate_email


logger = logging.getLogger('pizza_delivery_bot')


class TgDialogBot(object):

    def __init__(self, tg_token, states_functions, redis_conn, motlin_params, yandex_api_key):
        self.updater = Updater(token=tg_token)
        self.job = self.updater.job_queue
        self.updater.dispatcher.add_handler(CallbackQueryHandler(self.handle_users_reply))
        self.updater.dispatcher.add_handler(MessageHandler(Filters.text, self.handle_users_reply))
        self.updater.dispatcher.add_handler(MessageHandler(Filters.location, self.handle_geodata))
        self.updater.dispatcher.add_handler(CommandHandler('start', self.handle_users_reply))
        self.updater.dispatcher.add_error_handler(self.error)
        self.states_functions = states_functions
        self.redis_conn, self.ya_api_key, self.motlin_params = redis_conn, yandex_api_key, motlin_params
        self.motlin_token, self.token_expires = None, 0

    def start(self):
        self.redis_conn.clear_db()
        self.updater.start_polling()

    def handle_geodata(self, bot, update):
        next_state = self.states_functions['HANDLE_WAITING'](
            bot,
            update,
            motlin_token=self.motlin_token,
            redis_conn=self.redis_conn,
            ya_api_key=self.ya_api_key
        )
        self.redis_conn.add_value(update.message.chat_id, 'state', next_state)

    def update_motlin_token(self):
        if self.token_expires < datetime.now().timestamp():
            self.motlin_token, self.token_expires = motlin_lib.get_moltin_access_token(
                client_secret=self.motlin_params['MOLTIN_CLIENT_SECRET'],
                client_id=self.motlin_params['MOLTIN_CLIENT_ID']
            )

    def handle_users_reply(self, bot, update):
        self.update_motlin_token()
        if update.message:
            user_reply = update.message.text
            chat_id = update.message.chat_id
        elif update.callback_query:
            user_reply = update.callback_query.data
            chat_id = update.callback_query.message.chat_id
        else:
            return

        if user_reply == '/start':
            user_state = 'START'
        else:
            user_state = self.redis_conn.get_value(chat_id, 'state')

        state_handler = self.states_functions[user_state]
        next_state = state_handler(
            bot,
            update,
            self.motlin_token,
            self.redis_conn,
            self.ya_api_key,
            self.job
        )
        self.redis_conn.add_value(chat_id, 'state', next_state)

    def error(self, bot, update, error):
        logger.exception(f'Ошибка бота: {error}')


def start(bot, update, *args):
    motlin_token, redis_conn = args[:2]
    current_page = redis_conn.get_value(update.message.chat_id, 'current_page')
    show_store_menu(bot, update.message.chat_id, motlin_token, page=current_page)
    return 'HANDLE_MENU'


def handle_menu(bot, update, *args):
    motlin_token, redis_conn = args[:2]
    query = update.callback_query
    chat_id = query.message.chat_id
    if query.data == str(chat_id):
        show_products_in_cart(bot, chat_id, motlin_token, query.message.message_id)
        return 'HANDLE_CART'
    elif query.data.isdecimal():
        redis_conn.add_value(chat_id, 'current_page', query.data)
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


def handle_description(bot, update, *args):
    motlin_token, redis_conn = args[:2]
    query = update.callback_query
    chat_id = query.message.chat_id
    if query.data == 'HANDLE_MENU':
        current_page = redis_conn.get_value(chat_id, 'current_page')
        show_store_menu(bot, chat_id, motlin_token, query.message.message_id, current_page)
        return query.data
    elif query.data == str(chat_id):
        show_products_in_cart(bot, chat_id, motlin_token, query.message.message_id)
        return 'HANDLE_CART'
    else:
        add_product_to_cart(chat_id, motlin_token, query.data, query)
        return 'HANDLE_DESCRIPTION'


def handle_cart(bot, update, *args):
    motlin_token, redis_conn = args[:2]
    query = update.callback_query
    chat_id = query.message.chat_id
    if query.data == 'HANDLE_MENU':
        current_page = redis_conn.get_value(chat_id, 'current_page')
        show_store_menu(bot, chat_id, motlin_token, query.message.message_id, current_page)
        return query.data
    elif query.data == str(chat_id):
        bot.send_message(chat_id=chat_id, text='Пришлите, пожалуйста, Ваш адрес или геолокацию')
        return 'HANDLE_WAITING'
    else:
        motlin_lib.delete_from_cart(motlin_token, chat_id, query.data)
        show_products_in_cart(bot, chat_id, motlin_token, query.message.message_id)
        return 'HANDLE_CART'


def waiting_email(bot, update, *args):
    motlin_token, redis_conn = args[:2]
    query = update.callback_query
    if query and query.data == 'HANDLE_MENU':
        finish_order(bot, query.message.chat_id, query.message.message_id)
        return query.data
    elif query and query.data == 'WAITING_EMAIL':
        bot.send_message(chat_id=query.message.chat_id, text='Пришлите, пожалуйста, Ваш email')
        return query.data
    elif update.message.text and validate_email(update.message.text):
        if not motlin_lib.get_customer_id(motlin_token, update.message.text):
            motlin_lib.add_new_customer(motlin_token, update.message.text)
        confirm_email(bot, update.message.chat_id, motlin_token, update.message.text)
        return 'WAITING_EMAIL'
    else:
        bot.send_message(chat_id=update.message.chat_id, text='Вы ввели не корректный email. Поробуйте еще раз:')
        return 'WAITING_EMAIL'


def handle_waiting(bot, update, *args):
    motlin_token, redis_conn, ya_api_key = args[:3]
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
            longitude, latitude = geo_lib.fetch_coordinates(ya_api_key, update.message.text)
            customer_address = update.message.text
        elif update.message.location:
            longitude, latitude = update.message.location.longitude, update.message.location.latitude
            customer_address = geo_lib.fetch_address(ya_api_key, longitude, latitude)
        if not longitude == latitude is None:
            nearest_address = find_nearest_address(motlin_token, longitude, latitude)
            confirm_deliviry(bot, update.message.chat_id, motlin_token, nearest_address)
            redis_conn.add_value(update.message.chat_id, 'nearest_pizzeria', nearest_address['address'])
            motlin_load.save_address(
                motlin_token,
                'customeraddress',
                'customerid',
                str(update.message.chat_id),
                address={
                    'address': customer_address,
                    'longitude': longitude,
                    'latitude': latitude,
                    'customerid': str(update.message.chat_id)
                }
            )
        else:
            bot.send_message(chat_id=update.message.chat_id, text='Вы ввели не корректную геопозицию. Поробуйте еще раз:')
        return 'HANDLE_DELIVERY'


def handle_delivery(bot, update, *args):
    motlin_token, redis_conn, ya_api_key, job_queue = args
    query = update.callback_query
    chat_id = query.message.chat_id
    pizzeria_address = motlin_lib.get_address(
        motlin_token,
        'pizzeria',
        'address',
        redis_conn.get_value(chat_id, 'nearest_pizzeria')
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
        job_queue.run_once(show_reminder, 60, context=chat_id)
        return 'HANDLE_DELIVERY'
    else:
        if pizzeria_address:
            bot.send_location(chat_id=chat_id, latitude=pizzeria_address['latitude'], longitude=pizzeria_address['longitude'])
        message = f'Благодарим за заказ. После оплаты вы сможете забрать его по адресу: {pizzeria_address["address"]}'
        bot.send_message(chat_id=chat_id, text=message)
        return 'HANDLE_DELIVERY'


def launch_store_bot(states_functions, motlin_params):
    try:
        yandex_api_key = os.getenv('YANDEX_API_KEY')
        redis_conn = redis_lib.RedisDb(
            os.getenv('REDIS_HOST'),
            os.getenv('REDIS_PORT'),
            os.getenv('REDIS_PASSWORD')
        )
        bot = TgDialogBot(
            os.getenv('TG_ACCESS_TOKEN'),
            states_functions,
            redis_conn,
            motlin_params,
            yandex_api_key
        )
        bot.start()
    except Exception as error:
        logger.exception(f'Ошибка бота: {error}')
        launch_store_bot(states_functions, motlin_params)


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
        'WAITING_EMAIL': waiting_email,
        'HANDLE_WAITING': handle_waiting,
        'HANDLE_DELIVERY': handle_delivery
    }

    motlin_params = {
        'MOLTIN_CLIENT_ID': os.getenv('MOLTIN_CLIENT_ID'),
        'MOLTIN_CLIENT_SECRET': os.getenv('MOLTIN_CLIENT_SECRET')
    }

    launch_store_bot(states_functions, motlin_params)


if __name__ == '__main__':
    main()
