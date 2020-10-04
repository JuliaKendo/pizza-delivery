import os

from datetime import datetime
from dotenv import load_dotenv

from libs import motlin_lib
from libs import redis_lib

from flask import Flask, request

from fb_bot_events import add_product_to_cart, show_notification_adding_to_cart
from fb_bot_events import show_catalog, show_products_in_cart


START_CATEGORY_SLUG = 'Populiarnye'


class FbDialogBot(object):

    def __init__(self, fb_token, states_functions, **params):
        self.app = Flask(__name__)
        self.fb_token = fb_token
        self.states_functions = states_functions
        self.params = params
        self.app.route('/', methods=['GET'])(self.verify)
        self.app.route('/', methods=['POST'])(self.webhook)
        self.motlin_token, self.token_expires = None, 0

    def update_motlin_token(self):
        if self.token_expires < datetime.now().timestamp():
            self.motlin_token, self.token_expires = motlin_lib.get_moltin_access_token(
                client_secret=self.params['motlin_client_secret'],
                client_id=self.params['motlin_client_id']
            )

    def verify(self):
        if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.challenge"):
            if not request.args.get("hub.verify_token") == os.environ['VERIFY_TOKEN']:
                return "Verification token mismatch", 403
            return request.args["hub.challenge"], 200

        return "Hello world", 200

    def webhook(self):
        data = request.get_json()
        if data["object"] == "page":
            for entry in data["entry"]:
                for messaging_event in entry["messaging"]:
                    self.handle_users_reply(messaging_event)

        return "ok", 200

    def handle_users_reply(self, messaging_event):
        self.update_motlin_token()
        sender_id = messaging_event['sender']['id']
        recipient_id = messaging_event['recipient']['id']
        if messaging_event.get('message'):
            message = messaging_event['message']['text']
        elif messaging_event.get('postback'):
            message = messaging_event['postback']['payload']
        else:
            return

        if message == '/start':
            user_state = 'HANDLE_MENU'
        else:
            user_state = self.params['redis_conn'].get_value(sender_id, 'state')

        state_handler = self.states_functions[user_state]
        next_state = state_handler(self.fb_token, sender_id, self.motlin_token, message, self.params)
        self.params['redis_conn'].add_value(sender_id, 'state', next_state)

    def run(self):
        self.app.run(debug=True)


def handle_menu(fb_token, chat_id, motlin_token, message, params):
    if 'PRODUCT_' in message:
        product_id = message.replace('PRODUCT_', '')
        add_product_to_cart(chat_id, motlin_token, product_id)
        show_notification_adding_to_cart(fb_token, chat_id, motlin_token, product_id)
        return 'HANDLE_MENU'
    elif 'CART_' in message:
        return handle_description(fb_token, chat_id, motlin_token, message, params)
    else:
        current_category = message.replace('CATEGORY_', '') if 'CATEGORY_' in message else START_CATEGORY_SLUG
        show_catalog(fb_token, chat_id, motlin_token, current_category)
        return 'HANDLE_MENU'


def handle_description(fb_token, chat_id, motlin_token, message, params):
    if 'REMOVE_' in message:
        product_id = message.replace('REMOVE_', '')
        motlin_lib.delete_from_cart(motlin_token, chat_id, product_id)
        show_products_in_cart(fb_token, chat_id, motlin_token)
        return 'HANDLE_DESCRIPTION'
    elif 'PRODUCT_' in message:
        product_id = message.replace('PRODUCT_', '')
        add_product_to_cart(chat_id, motlin_token, product_id)
        show_products_in_cart(fb_token, chat_id, motlin_token)
        return 'HANDLE_DESCRIPTION'
    elif 'HANDLE_MENU' in message:
        show_catalog(fb_token, chat_id, motlin_token, START_CATEGORY_SLUG)
        return 'HANDLE_MENU'
    else:
        show_products_in_cart(fb_token, chat_id, motlin_token)
        return 'HANDLE_DESCRIPTION'


def main():
    load_dotenv()

    states_functions = {
        'HANDLE_MENU': handle_menu,
        'HANDLE_DESCRIPTION': handle_description
    }

    redis_conn = redis_lib.RedisDb(
        os.getenv('REDIS_HOST'),
        os.getenv('REDIS_PORT'),
        os.getenv('REDIS_PASSWORD')
    )

    bot = FbDialogBot(
        os.environ['FACEBOOK_TOKEN'],
        states_functions,
        redis_conn=redis_conn,
        motlin_client_id=os.getenv('MOLTIN_CLIENT_ID'),
        motlin_client_secret=os.getenv('MOLTIN_CLIENT_SECRET')
    )
    bot.run()


if __name__ == '__main__':
    main()
