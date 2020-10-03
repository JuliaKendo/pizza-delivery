import os
import requests

from datetime import datetime
from dotenv import load_dotenv

from libs import motlin_lib

from flask import Flask, request


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
                    if messaging_event.get("message"):
                        self.handle_users_reply(messaging_event)

        return "ok", 200

    def handle_users_reply(self, messaging_event):
        self.update_motlin_token()
        sender_id = messaging_event["sender"]["id"]
        # recipient_id = messaging_event["recipient"]["id"]
        # message_text = messaging_event["message"]["text"]

        user_state = 'HANDLE_MENU'
        state_handler = self.states_functions[user_state]
        state_handler(self.fb_token, sender_id, self.motlin_token, self.params)

    def run(self):
        self.app.run(debug=True)


def send_message(fb_token, recipient_id, request_content):
    params = {'access_token': fb_token}
    headers = {'Content-Type': 'application/json'}
    request_content['recipient'] = {
        'id': recipient_id
    }

    response = requests.post(
        'https://graph.facebook.com/v2.6/me/messages',
        params=params, headers=headers, json=request_content
    )
    response.raise_for_status()


def get_menu_card(motlin_token, recipient_id):
    logo_id = motlin_lib.get_item_id(motlin_token, 'files', field='file_name', value='logo.png')
    menu_card = {
        'title': 'Меню',
        'subtitle': 'Здесь вы можете выбрать один из варивнтов',
        'image_url': motlin_lib.get_file_link(motlin_token, logo_id),
        'buttons': [
            {
                'type': 'postback',
                'title': 'Корзина',
                'payload': recipient_id
            },
            {
                'type': 'postback',
                'title': 'Оформить заказ',
                'payload': recipient_id
            }
        ]
    }
    return menu_card


def get_categories_card(motlin_token, recipient_id, excepted_category_slug):
    categories = [category for category in motlin_lib.get_categories(motlin_token) if category['slug'] != excepted_category_slug]
    category_image_id = motlin_lib.get_item_id(motlin_token, 'files', field='file_name', value='category.png')
    buttons = map(
        lambda category: {
            'type': 'postback',
            'title': category['name'],
            'payload': category['id']
        },
        categories
    )
    categories_card = {
        'title': 'Не нашли нужную пиццу?',
        'subtitle': 'Остальные пиццы можно найти в одной из следующих категорий:',
        'image_url': motlin_lib.get_file_link(motlin_token, category_image_id),
        'buttons': list(buttons)
    }
    return categories_card


def show_catalog(fb_token, recipient_id, motlin_token, params):
    category_id = motlin_lib.get_item_id(motlin_token, 'categories', field='slug', value='Populiarnye')
    products_by_category = motlin_lib.get_products_by_category_id(motlin_token, category_id)
    products_description = map(
        lambda product: {
            'title': f'{product["name"]} ({product["price"][0]["amount"]} {product["price"][0]["currency"]})',
            'subtitle': product['description'],
            'image_url': motlin_lib.get_product_info(motlin_token, product['id'])[-1],
            'buttons': [
                {
                    'type': 'postback',
                    'title': 'Положить в корзину',
                    'payload': product['id']
                }
            ]
        }, products_by_category
    )
    catalog = list(products_description)
    catalog.insert(0, get_menu_card(motlin_token, recipient_id))
    catalog.append(get_categories_card(motlin_token, recipient_id, 'Populiarnye'))
    request_content = {
        'message': {
            'attachment': {
                'type': 'template',
                'payload': {
                    'template_type': 'generic',
                    'elements': catalog
                }
            }
        }
    }
    send_message(fb_token, recipient_id, request_content)


def main():
    load_dotenv()

    states_functions = {'HANDLE_MENU': show_catalog}

    bot = FbDialogBot(
        os.environ['FACEBOOK_TOKEN'],
        states_functions,
        motlin_client_id=os.getenv('MOLTIN_CLIENT_ID'),
        motlin_client_secret=os.getenv('MOLTIN_CLIENT_SECRET')
    )
    bot.run()


if __name__ == '__main__':
    main()
