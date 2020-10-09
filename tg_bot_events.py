
from libs import geo_lib
from libs import motlin_lib
import textwrap

from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

LIMIT_PRODS_PER_PAGE = 5


def clear_settings_and_task_queue(chat_id, params):
    params['redis_conn'].del_value(chat_id)
    for job in params['job'].jobs():
        job.schedule_removal()


def get_delivery_time(redis_conn, chat_id, end_of_period):
    delivery_time = redis_conn.get_value(chat_id, 'delivery_time')
    if not delivery_time:
        return datetime.now() + timedelta(seconds=end_of_period)
    else:
        return datetime.fromtimestamp(float(delivery_time))


def delete_messages(bot, chat_id, message_id, message_numbers=1):
    if not message_id:
        return
    user_id = chat_id.replace('tg', '') if 'tg' in chat_id else str(chat_id)
    for offset_id in range(message_numbers):
        bot.delete_message(chat_id=user_id, message_id=int(message_id) - offset_id)


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
            InlineKeyboardButton('Пред.', callback_data='%d' % (page - 1)),
            InlineKeyboardButton('След.', callback_data='%d' % (page + 1))
        ])
    elif page == 1:
        keyboard.append([
            InlineKeyboardButton('След.', callback_data='%d' % (page + 1))
        ])
    elif page >= max_pages:
        keyboard.append([
            InlineKeyboardButton('Пред.', callback_data='%d' % (page - 1))
        ])
    return InlineKeyboardMarkup(keyboard)


def get_product_card_menu(access_token, product_id):
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
    keyboard.append([InlineKeyboardButton('Оформить заказ', callback_data=chat_id)])
    return InlineKeyboardMarkup(keyboard)


def get_customers_menu(access_token, chat_id, add_continue_button=False):
    keyboard = [
        [
            InlineKeyboardButton('эл. почта', callback_data='CUSTOMERS_MAIL'),
            InlineKeyboardButton('телефон', callback_data='CUSTOMERS_PHONE')
        ]
    ]
    if add_continue_button:
        keyboard.append([InlineKeyboardButton('продолжить', callback_data='HANDLE_WAITING')])
    return InlineKeyboardMarkup(keyboard)


def get_delivery_menu(access_token, chat_id, delivery_price=0, only_pick_up=False):
    keyboard = [[InlineKeyboardButton('Самовывоз', callback_data='PICKUP_DELIVERY')]]
    if not only_pick_up:
        callback_data = f'COURIER_DELIVERY{delivery_price if delivery_price else ""}'
        keyboard.append([InlineKeyboardButton('Доставка', callback_data=callback_data)])
    return InlineKeyboardMarkup(keyboard)


def get_courier_menu(access_token, chat_id):
    keyboard = [[InlineKeyboardButton('Доставлен!', callback_data=f'DELIVEREDTO{chat_id}')]]
    return InlineKeyboardMarkup(keyboard)


def get_courier_confirmation_menu(customer_chat_id):
    keyboard = [
        [
            InlineKeyboardButton('Да', callback_data=f'DELIVEREDYES{customer_chat_id}'),
            InlineKeyboardButton('Нет', callback_data=customer_chat_id)
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_payment_menu():
    keyboard = [
        [InlineKeyboardButton('Наличные', callback_data='CASH_PAYMENT')],
        [InlineKeyboardButton('Банковская карта', callback_data='CARD_PAYMENT')]
    ]
    return InlineKeyboardMarkup(keyboard)


def show_store_menu(bot, chat_id, motlin_token, delete_message_id=0, page=None):
    reply_markup = get_store_menu(motlin_token, chat_id, page)
    bot.send_message(
        chat_id=chat_id.replace('tg', ''),
        text="Пожалуйста, выберите пиццу:",
        reply_markup=reply_markup
    )
    delete_messages(bot, chat_id, delete_message_id)


def show_product_card(bot, chat_id, motlin_token, product_id, delete_message_id=0):
    product_caption, product_image = motlin_lib.get_product_info(motlin_token, product_id)
    reply_markup = get_product_card_menu(motlin_token, product_id)
    bot.send_photo(
        chat_id=chat_id.replace('tg', ''),
        photo=product_image,
        caption=product_caption,
        reply_markup=reply_markup,
        parse_mode='html'
    )
    delete_messages(bot, chat_id, delete_message_id)


def add_product_to_cart(chat_id, motlin_token, product_id, query):
    product_quantity = motlin_lib.get_quantity_product_in_cart(motlin_token, chat_id, product_id)
    product_quantity += 1
    motlin_lib.put_into_cart(motlin_token, chat_id, product_id, product_quantity)
    query.answer("Товар добавлен в корзину")


def show_products_in_cart(bot, chat_id, motlin_token, delete_message_id=0):
    cart_info = motlin_lib.get_cart_info(motlin_token, chat_id)
    reply_markup = get_cart_menu(motlin_token, chat_id)
    bot.send_message(
        chat_id=chat_id.replace('tg', ''),
        text=cart_info,
        reply_markup=reply_markup,
        parse_mode='html'
    )
    delete_messages(bot, chat_id, delete_message_id)


def show_customers_menu(bot, chat_id, motlin_token, delete_message_id=0):
    customer_address = motlin_lib.get_address(motlin_token, 'customeraddress', 'customerid', str(chat_id))
    if customer_address:
        reply_markup = get_customers_menu(motlin_token, chat_id, customer_address['telephone'] and customer_address['email'])
    else:
        reply_markup = get_customers_menu(motlin_token, chat_id)
    bot.send_message(
        chat_id=chat_id.replace('tg', ''),
        text='Введите контактные данные:',
        reply_markup=reply_markup
    )
    delete_messages(bot, chat_id, delete_message_id)


def find_nearest_address(motlin_token, longitude, latitude):
    addresses = motlin_lib.get_pizzeria_entries(motlin_token)
    geo_lib.calculate_distance(addresses, longitude, latitude)
    return min(addresses, key=lambda address: address['distance'])


def save_customer_phone(bot, chat_id, motlin_token, customer_phone):
    motlin_lib.save_address(
        motlin_token, 'customeraddress',
        'customerid', chat_id,
        address={
            'telephone': customer_phone,
            'customerid': chat_id
        }
    )


def save_customer_email(bot, chat_id, motlin_token, customer_phone):
    motlin_lib.save_address(
        motlin_token, 'customeraddress',
        'customerid', chat_id,
        address={
            'email': customer_phone,
            'customerid': chat_id
        }
    )


def save_customer_address(bot, chat_id, motlin_token, customer_address, longitude, latitude, address_decryption):
    motlin_lib.save_address(
        motlin_token,
        'customeraddress',
        'customerid',
        chat_id,
        address={
            'address': customer_address,
            'longitude': longitude,
            'latitude': latitude,
            'customerid': chat_id,
            'country': address_decryption['CountryName'],
            'county': address_decryption['AdministrativeAreaName'],
            'city': address_decryption['LocalityName']
        }
    )


def choose_deliviry(bot, chat_id, motlin_token, nearest_address, delete_message_id=0):
    if nearest_address['distance'] <= 0.5:
        reply_markup = get_delivery_menu(motlin_token, chat_id)
        bot.send_message(
            chat_id=chat_id.replace('tg', ''),
            text=textwrap.dedent(f'''
                Может заберете заказ из нашей пицерии неподалеку?
                Она всего в {int(nearest_address['distance']*1000)} метрах от Вас.
                Вот ее адрес: {nearest_address['address']}.
                А можем и бесплатно доставить, нам не сложно.'''),
            reply_markup=reply_markup
        )
    elif nearest_address['distance'] > 0.5 and nearest_address['distance'] <= 5:
        reply_markup = get_delivery_menu(motlin_token, chat_id, 100)
        bot.send_message(
            chat_id=chat_id.replace('tg', ''),
            text=textwrap.dedent('''
                Похоже придется ехать до Вас на самокате.
                Доставка будет стоить 100 RUB.
                Доставляем или самовывоз?'''),
            reply_markup=reply_markup
        )
    elif nearest_address['distance'] > 5 and nearest_address['distance'] <= 20:
        reply_markup = get_delivery_menu(motlin_token, chat_id, 300)
        bot.send_message(
            chat_id=chat_id.replace('tg', ''),
            text=textwrap.dedent('''
                Доставка будет стоить 300 RUB.
                Доставляем или самовывоз?'''),
            reply_markup=reply_markup
        )
    else:
        reply_markup = get_delivery_menu(motlin_token, chat_id, 0, True)
        bot.send_message(
            chat_id=chat_id.replace('tg', ''),
            text=textwrap.dedent(f'''
                Простите, но так далеко мы пиццу не доставим.
                Ближайшая пиццерия находится в {int(nearest_address['distance'])} км. от вас.'''),
            reply_markup=reply_markup
        )
    delete_messages(bot, chat_id, delete_message_id)


def confirm_deliviry(bot, chat_id, customer_chat_id, delete_message_id=0):
    reply_markup = get_courier_confirmation_menu(customer_chat_id)
    message = 'Подтвердите доставку:'
    bot.send_message(chat_id=chat_id.replace('tg', ''), text=message, reply_markup=reply_markup)
    delete_messages(bot, chat_id, delete_message_id, 2)


def send_or_update_courier_messages(bot, job):
    params_of_courier_messages = [value for value in job.context.values()]
    message_id = job.context['redis_conn'].get_value(job.context['courier_id'], job.context['chat_id'])
    if message_id:
        update_courier_message(bot, message_id, job, params_of_courier_messages)
    else:
        send_courier_message(bot, params_of_courier_messages)


def update_courier_message(bot, message_id, job, params_of_courier_message):
    chat_id, delivery_chat_id, motlin_token, customer_address, \
        delivery_price, cash, redis_conn, delivery_time = params_of_courier_message
    courier_id = delivery_chat_id.replace('tg', '')
    rest_of_delivery_time = int((delivery_time - datetime.now()).seconds / 60)
    reply_markup = get_courier_menu(motlin_token, chat_id)
    cart_info, currency, amount = motlin_lib.get_payment_info(motlin_token, str(chat_id))
    if rest_of_delivery_time > 0:
        message = '\n'.join(
            [
                cart_info,
                f'Сумма заказа: {amount} {currency}',
                f'Доставка {delivery_price} {currency}' if delivery_price else '',
                'Наличными при получении' if cash else '',
                f'Доставить через {rest_of_delivery_time} минут'
            ]
        )
    else:
        message = '\n'.join(
            [
                cart_info,
                f'Сумма заказа: {amount} {currency}',
                'Доставка просрочена'
            ]
        )
        job.schedule_removal()
    bot.edit_message_text(
        chat_id=courier_id, message_id=int(message_id),
        text=message, reply_markup=reply_markup
    )


def send_courier_message(bot, params_of_courier_message):
    chat_id, delivery_chat_id, motlin_token, customer_address, \
        delivery_price, cash, redis_conn, delivery_time = params_of_courier_message
    courier_id = delivery_chat_id.replace('tg', '')
    rest_of_delivery_time = int((delivery_time - datetime.now()).seconds / 60)
    bot.send_location(chat_id=courier_id, latitude=customer_address['latitude'], longitude=customer_address['longitude'])
    reply_markup = get_courier_menu(motlin_token, chat_id)
    cart_info, currency, amount = motlin_lib.get_payment_info(motlin_token, chat_id)
    message = '\n'.join(
        [
            cart_info,
            f'Сумма заказа: {amount} {currency}',
            f'Доставка {delivery_price} {currency}' if delivery_price else '',
            'Наличными при получении' if cash else '',
            f'Доставить через {rest_of_delivery_time} минут'
        ]
    )
    sended_message = bot.send_message(chat_id=courier_id, text=message, reply_markup=reply_markup)
    redis_conn.add_value(delivery_chat_id, chat_id, sended_message.message_id)
    redis_conn.add_value(chat_id, 'delivery_time', delivery_time.timestamp())


def choose_payment_type(bot, chat_id, delete_message_id=0):
    reply_markup = get_payment_menu()
    message = 'Выберите вид оплаты:'
    bot.send_message(chat_id=chat_id.replace('tg', ''), text=message, reply_markup=reply_markup)
    delete_messages(bot, chat_id, delete_message_id)


def show_reminder(bot, job):
    message = 'Приятного аппетита!\n\nЕсли у вас еще нет пиццы, мы обязательно скоро привезем ее!'
    bot.send_message(chat_id=job.context.replace('tg', ''), text=message)


def confirm_order(bot, chat_id, motlin_token, cash_payment=False, delete_message_id=0):
    user_id = chat_id.replace('tg', '')
    order_id = motlin_lib.create_order(motlin_token, chat_id)
    if order_id:
        transaction_id = motlin_lib.set_order_payment(motlin_token, order_id)
        motlin_lib.confirm_order_payment(motlin_token, order_id, transaction_id)
    if cash_payment:
        bot.send_message(chat_id=user_id, text='Благодарим! Ваш заказ изготавливается.')
    else:
        bot.send_message(chat_id=user_id, text='Благодарим за оплату! Ваш заказ изготавливается.')
    delete_messages(bot, chat_id, delete_message_id)
    return order_id
