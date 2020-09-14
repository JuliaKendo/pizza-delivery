import geo_lib
import motlin_lib
import textwrap
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

LIMIT_PRODS_PER_PAGE = 5


def get_store_menu(access_token, chat_id, page=None):
    offset = LIMIT_PRODS_PER_PAGE * (int(page) - 1 if page else 0)
    all_products, max_pages, page = motlin_lib.get_products(access_token, offset, LIMIT_PRODS_PER_PAGE)
    products_in_cart = {
        cart_item['product_id']: cart_item['quantity']
        for cart_item in motlin_lib.get_cart_items(access_token, chat_id)
    }
    keyboard = [
        [InlineKeyboardButton(
            '%s %s' % (
                products['name'], '({} шт.)'.format(products_in_cart[products['id']]) if products_in_cart.get(products['id']) else ''
            ), callback_data=products['id']
        )] for products in all_products
    ]
    keyboard.append([InlineKeyboardButton('Корзина', callback_data=chat_id)])
    if max_pages == 1:
        return InlineKeyboardMarkup(keyboard)
    if page > 1 and page < max_pages:
        keyboard.append([
            InlineKeyboardButton('<', callback_data='%d' % (page - 1)),
            InlineKeyboardButton('>', callback_data='%d' % (page + 1))
        ])
    elif page == 1:
        keyboard.append([
            InlineKeyboardButton('>', callback_data='%d' % (page + 1))
        ])
    elif page >= max_pages:
        keyboard.append([
            InlineKeyboardButton('<', callback_data='%d' % (page - 1))
        ])
    return InlineKeyboardMarkup(keyboard)


def get_product_card_menu(access_token, chat_id, product_id):
    keyboard = [
        [InlineKeyboardButton('Положить в корзину', callback_data=product_id)],
        [InlineKeyboardButton('В меню', callback_data='HANDLE_MENU')]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_cart_menu(access_token, chat_id):
    cart_items = motlin_lib.get_cart_items(access_token, chat_id)
    keyboard = [
        [
            InlineKeyboardButton(
                'Убрать из корзины %s' % cart_item['name'],
                callback_data=cart_item['id']
            )
        ] for cart_item in cart_items
    ]
    keyboard.append([InlineKeyboardButton('В меню', callback_data='HANDLE_MENU')])
    keyboard.append([InlineKeyboardButton('Оплата', callback_data=chat_id)])
    return InlineKeyboardMarkup(keyboard)


def get_delivery_menu(access_token, chat_id, only_pick_up=False):
    keyboard = [[InlineKeyboardButton('Самовывоз', callback_data=chat_id)]]
    if not only_pick_up:
        keyboard.append([InlineKeyboardButton('Доставка', callback_data='HANDLE_DELIVERY')])
    return InlineKeyboardMarkup(keyboard)


def get_confirm_menu(access_token):
    keyboard = [
        [InlineKeyboardButton('Верно', callback_data='HANDLE_MENU')],
        [InlineKeyboardButton('Не верно', callback_data='WAITING_EMAIL')]
    ]
    return InlineKeyboardMarkup(keyboard)


def show_store_menu(bot, chat_id, motlin_token, delete_message_id=0, page=None):
    reply_markup = get_store_menu(motlin_token, chat_id, page)
    bot.send_message(chat_id=chat_id, text="Please choise:", reply_markup=reply_markup)
    if delete_message_id:
        bot.delete_message(chat_id=chat_id, message_id=delete_message_id)


def show_product_card(bot, chat_id, motlin_token, product_id, delete_message_id=0):
    product_caption, product_image = motlin_lib.get_product_info(motlin_token, product_id)
    reply_markup = get_product_card_menu(motlin_token, chat_id, product_id)
    bot.send_photo(
        chat_id=chat_id,
        photo=product_image,
        caption=product_caption,
        reply_markup=reply_markup,
        parse_mode='html'
    )
    if delete_message_id:
        bot.delete_message(chat_id=chat_id, message_id=delete_message_id)


def add_product_to_cart(chat_id, motlin_token, product_id, query):
    product_quantity = motlin_lib.get_quantity_product_in_cart(motlin_token, chat_id, product_id)
    product_quantity += 1
    motlin_lib.put_into_cart(motlin_token, chat_id, product_id, product_quantity)
    query.answer("Товар добавлен в корзину")


def show_products_in_cart(bot, chat_id, motlin_token, delete_message_id=0):
    cart_info = motlin_lib.get_cart_info(motlin_token, str(chat_id))
    reply_markup = get_cart_menu(motlin_token, chat_id)
    bot.send_message(
        chat_id=chat_id,
        text=cart_info,
        reply_markup=reply_markup,
        parse_mode='html'
    )
    if delete_message_id:
        bot.delete_message(chat_id=chat_id, message_id=delete_message_id)


def confirm_email(bot, chat_id, motlin_token, customer_email):
    reply_markup = get_confirm_menu(motlin_token)
    bot.send_message(
        chat_id=chat_id,
        text='Ваш еmail: %s' % customer_email,
        reply_markup=reply_markup)


def find_nearest_address(motlin_token, longitude, latitude):
    addresses = motlin_lib.get_entries(motlin_token, 'pizzeria')
    geo_lib.calculate_distance(addresses, longitude, latitude)
    return min(addresses, key=lambda address: address['distance'])


def confirm_deliviry(bot, chat_id, motlin_token, nearest_address, delete_message_id=0):
    if nearest_address['distance'] <= 0.5:
        reply_markup = get_delivery_menu(motlin_token, chat_id)
        bot.send_message(
            chat_id=chat_id,
            text=textwrap.dedent(f'''
                Может заберете заказ из нашей пицерии неподалеку?
                Она всего в {int(nearest_address['distance']*1000)} метрах от Вас.
                Вот ее адрес: {nearest_address['address']}.
                А можем и бесплатно доставить, нам не сложно.'''),
            reply_markup=reply_markup
        )
    elif nearest_address['distance'] > 0.5 and nearest_address['distance'] <= 5:
        reply_markup = get_delivery_menu(motlin_token, chat_id)
        bot.send_message(
            chat_id=chat_id,
            text=textwrap.dedent('''
                Похоже придется ехать до Вас на самокате.
                Доставка будет стоить 100 RUB.
                Доставляем или самовывоз?'''),
            reply_markup=reply_markup
        )
    elif nearest_address['distance'] > 5 and nearest_address['distance'] <= 20:
        reply_markup = get_delivery_menu(motlin_token, chat_id)
        bot.send_message(
            chat_id=chat_id,
            text=textwrap.dedent('''
                Доставка будет стоить 300 RUB.
                Доставляем или самовывоз?'''),
            reply_markup=reply_markup
        )
    else:
        reply_markup = get_delivery_menu(motlin_token, chat_id, True)
        bot.send_message(
            chat_id=chat_id,
            text=textwrap.dedent(f'''
                Простите, но так далеко мы пиццу не доставим.
                Ближайщая пицерия аж в {int(nearest_address['distance'])} км. от вас.'''),
            reply_markup=reply_markup
        )
    if delete_message_id:
        bot.delete_message(chat_id=chat_id, message_id=delete_message_id)


def show_delivery_messages(bot, chat_id, delivery_chat_id, motlin_token, latitude, longitude, delete_message_id=0):
    cart_info = motlin_lib.get_cart_info(motlin_token, str(chat_id))
    bot.send_message(
        chat_id=delivery_chat_id,
        text=cart_info,
        parse_mode='html'
    )
    bot.send_location(chat_id=delivery_chat_id, latitude=latitude, longitude=longitude)
    if delete_message_id:
        bot.delete_message(chat_id=chat_id, message_id=delete_message_id)


def finish_order(bot, chat_id, delete_message_id=0):
    bot.send_message(chat_id=chat_id, text='Благодарим за заказ. Менеждер свяжется с Вами в бижайшее время.')
    bot.delete_message(chat_id=chat_id, message_id=delete_message_id)
