import json
import requests
from libs import motlin_lib

FILENAME_WITH_LOGO_IMAGE = 'logo.png'
FILENAME_WITH_LOGO_CART = 'cart.png'
FILENAME_WITH_CATEGORY_IMAGE = 'category.png'


def send_message(fb_token, chat_id, request_content):
    params = {'access_token': fb_token}
    headers = {'Content-Type': 'application/json'}
    request_content['recipient'] = {
        'id': chat_id.replace('fb', '')
    }

    response = requests.post(
        'https://graph.facebook.com/v2.6/me/messages',
        params=params, headers=headers, json=request_content
    )
    response.raise_for_status()


def get_menu_card(motlin_token):
    logo_id = motlin_lib.get_item_id(motlin_token, 'files', field='file_name', value=FILENAME_WITH_LOGO_IMAGE)
    menu_card = {
        'title': 'Меню',
        'subtitle': 'Здесь вы можете выбрать один из вариантов',
        'image_url': motlin_lib.get_file_link(motlin_token, logo_id),
        'buttons': [
            {
                'type': 'postback',
                'title': 'Корзина',
                'payload': 'CART'
            },
            {
                'type': 'postback',
                'title': 'Оформить заказ',
                'payload': 'ORDER'
            }
        ]
    }
    return menu_card


def get_cart_card(motlin_token, chat_id):
    logo_id = motlin_lib.get_item_id(motlin_token, 'files', field='file_name', value=FILENAME_WITH_LOGO_CART)
    menu_card = {
        'title': f'Ваш заказ на сумму {motlin_lib.get_cart_amount(motlin_token, chat_id)}',
        'subtitle': 'Выберите дальнейшие действия с корзиной:',
        'image_url': motlin_lib.get_file_link(motlin_token, logo_id),
        'buttons': [
            {
                'type': 'postback',
                'title': 'Самовывоз',
                'payload': f'PICKUP_DELIVERY'
            },
            {
                'type': 'postback',
                'title': 'Доставка',
                'payload': f'COURIER_DELIVERY'
            },
            {
                'type': 'postback',
                'title': 'В меню',
                'payload': 'HANDLE_MENU'
            }
        ]
    }
    return menu_card


def get_categories_card(motlin_token, excepted_category_slug):
    categories = [category for category in motlin_lib.get_categories(motlin_token) if category['slug'] != excepted_category_slug]
    category_image_id = motlin_lib.get_item_id(motlin_token, 'files', field='file_name', value=FILENAME_WITH_CATEGORY_IMAGE)
    return {
        'title': 'Не нашли нужную пиццу?',
        'subtitle': 'Остальные пиццы можно найти в одной из следующих категорий:',
        'image_url': motlin_lib.get_file_link(motlin_token, category_image_id),
        'buttons': [
            {
                'type': 'postback',
                'title': category['name'],
                'payload': f'CATEGORY_{category["slug"]}'
            } for category in categories
        ]
    }


def show_notification_adding_to_cart(fb_token, chat_id, motlin_token, product_id):
    product_info = motlin_lib.execute_get_request(
        f'https://api.moltin.com/v2/products/{product_id}',
        headers={'Authorization': motlin_token}
    )
    send_message(
        fb_token,
        chat_id,
        {
            'message': {
                'text': f'в корзину добавлена пицца {product_info["name"]}'
            }
        }
    )


def get_catalog_content(chat_id, motlin_token, current_category_slug):
    category_id = motlin_lib.get_item_id(motlin_token, 'categories', field='slug', value=current_category_slug)
    products_by_category = motlin_lib.get_products_by_category_id(motlin_token, category_id)
    catalog = [
        {
            'title': f'{product["name"]} ({product["price"][0]["amount"]} {product["price"][0]["currency"]})',
            'subtitle': product['description'],
            'image_url': motlin_lib.get_product_info(motlin_token, product['id'])[-1],
            'buttons': [
                {
                    'type': 'postback',
                    'title': 'Положить в корзину',
                    'payload': f'PRODUCT_{product["id"]}'
                }
            ]
        } for product in products_by_category
    ]
    return {
        'message': {
            'attachment': {
                'type': 'template',
                'payload': {
                    'template_type': 'generic',
                    'elements': [
                        get_menu_card(motlin_token),
                        *catalog,
                        get_categories_card(motlin_token, current_category_slug)
                    ]
                }
            }
        }
    }


def show_catalog(fb_token, chat_id, motlin_token, redis_conn, current_category_slug):
    request_content = redis_conn.get_value(chat_id, current_category_slug)
    if not request_content:
        request_content = get_catalog_content(chat_id, motlin_token, current_category_slug)
        redis_conn.add_value(chat_id, current_category_slug, json.dumps(request_content))
    else:
        request_content = json.loads(request_content)
    send_message(fb_token, chat_id, request_content)


def add_product_to_cart(chat_id, motlin_token, product_id):
    product_quantity = motlin_lib.get_quantity_product_in_cart(motlin_token, chat_id, product_id)
    product_quantity += 1
    motlin_lib.put_into_cart(motlin_token, chat_id, product_id, product_quantity)


def show_products_in_cart(fb_token, chat_id, motlin_token):
    cart_items = motlin_lib.get_cart_items(motlin_token, str(chat_id))
    cart_description = map(
        lambda cart_item: {
            'title': f'{cart_item["name"]} ({cart_item["quantity"]} шт.)',
            'subtitle': cart_item['description'],
            'image_url': motlin_lib.get_product_info(motlin_token, cart_item['product_id'])[-1],
            'buttons': [
                {
                    'type': 'postback',
                    'title': 'Добавить еще одну',
                    'payload': f'PRODUCT_{cart_item["product_id"]}'
                },
                {
                    'type': 'postback',
                    'title': 'Убрать из корзины',
                    'payload': f'REMOVE_{cart_item["id"]}'
                }
            ]
        }, cart_items
    )
    products_in_cart = list(cart_description)
    products_in_cart.insert(0, get_cart_card(motlin_token, chat_id))

    request_content = {
        'message': {
            'attachment': {
                'type': 'template',
                'payload': {
                    'template_type': 'generic',
                    'elements': products_in_cart
                }
            }
        }
    }
    send_message(fb_token, chat_id, request_content)
