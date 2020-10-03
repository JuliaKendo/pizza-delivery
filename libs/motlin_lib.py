import os
import json
import requests
from tqdm import tqdm
from slugify import slugify
from urllib.parse import urlparse


def get_moltin_access_token(client_secret, client_id):
    response = requests.post(
        'https://api.moltin.com/oauth/access_token',
        data={
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'client_credentials'
        }
    )
    response.raise_for_status()
    moltin_token = response.json()
    return moltin_token['access_token'], moltin_token['expires']


def execute_get_request(url, headers={}, data={}):
    response = requests.get(url, headers=headers, data=data)
    response.raise_for_status()
    return response.json()['data']


def get_item_id(access_token, item_type, **kwargs):
    urls = {
        'categories': 'https://api.moltin.com/v2/categories',
        'products': 'https://api.moltin.com/v2/products',
        'customers': 'https://api.moltin.com/v2/customers',
        'flows': 'https://api.moltin.com/v2/flows',
        'fields': 'https://api.moltin.com/v2/flows/%s/fields',
        'entries': 'https://api.moltin.com/v2/flows/%s/entries'
    }
    found_items = execute_get_request(
        urls[item_type] % kwargs['slug'] if kwargs.get('slug') else urls[item_type],
        {'Authorization': access_token}
    )
    found_item = [item['id'] for item in found_items if item[kwargs['field']] == kwargs['value']]
    return found_item[0] if found_item else None


def get_products(access_token, offset=0, limit_products_per_page=0):
    response = requests.get(
        'https://api.moltin.com/v2/products?page[limit]=%s&page[offset]=%s' % (limit_products_per_page, offset),
        headers={'Authorization': access_token}
    )

    response.raise_for_status()
    products = response.json()
    return (
        products['data'],
        products['meta']['page']['total'],
        products['meta']['page']['current']
    )


def add_new_product(access_token, product_characteristic):
    response = requests.post(
        f'https://api.moltin.com/v2/products',
        headers={'Authorization': access_token, 'Content-Type': 'application/json'},
        json={'data': product_characteristic}
    )
    response.raise_for_status()
    return response.json()['data']['id']


def update_product(access_token, product_id, product_characteristic):
    product_characteristic['id'] = product_id
    response = requests.put(
        f'https://api.moltin.com/v2/products/{product_id}',
        headers={'Authorization': access_token, 'Content-Type': 'application/json'},
        json={'data': product_characteristic}
    )
    response.raise_for_status()


def get_categories(access_token):
    categories = execute_get_request(
        f'https://api.moltin.com/v2/categories',
        headers={'Authorization': access_token}
    )
    return categories


def add_new_category(access_token, category_characteristic):
    response = requests.post(
        f'https://api.moltin.com/v2/categories',
        headers={'Authorization': access_token, 'Content-Type': 'application/json'},
        json={'data': category_characteristic}
    )
    response.raise_for_status()
    return response.json()['data']['id']


def update_category(access_token, category_id, category_characteristic):
    category_characteristic['id'] = category_id
    response = requests.put(
        f'https://api.moltin.com/v2/categories/{category_id}',
        headers={'Authorization': access_token, 'Content-Type': 'application/json'},
        json={'data': category_characteristic}
    )
    response.raise_for_status()


def load_file(access_token, product_id, image_file):
    response = requests.post(
        f'https://api.moltin.com/v2/files',
        headers={'Authorization': access_token},
        files={'file': open(image_file, 'rb'), 'public': True}
    )
    response.raise_for_status()
    add_product_image(access_token, product_id, response.json()['data']['id'])


def get_quantity_product_in_stock(access_token, product_id):
    product_data = execute_get_request(
        f'https://api.moltin.com/v2/inventories/{product_id}',
        headers={'Authorization': access_token}
    )
    return product_data['total']


def get_product_image(access_token, product_data):
    image_id = product_data['relationships']['main_image']['data']['id']
    product_data = execute_get_request(
        f'https://api.moltin.com/v2/files/{image_id}',
        headers={'Authorization': access_token}
    )
    return product_data['link']['href']


def add_product_image(access_token, product_id, image_id):
    response = requests.post(
        f'https://api.moltin.com/v2/products/{product_id}/relationships/main-image',
        headers={'Authorization': access_token, 'Content-Type': 'application/json'},
        json={'data': {'type': 'main_image', 'id': image_id}}
    )
    response.raise_for_status()


def get_product_info(access_token, product_id):
    product_data = execute_get_request(
        f'https://api.moltin.com/v2/products/{product_id}',
        headers={'Authorization': access_token}
    )
    product_image = get_product_image(access_token, product_data)
    name, description, currency, amount = (
        product_data['name'],
        product_data['description'],
        product_data['price'][0]['currency'],
        product_data['price'][0]['amount']
    )
    return (
        f'<b>{name}</b>\n\nстоимость: {amount} {currency}\n\n<i>{description}</i>',
        product_image
    )


def put_into_cart(access_token, cart_id, prod_id, quantity=1):
    response = requests.post(
        f'https://api.moltin.com/v2/carts/{cart_id}/items',
        headers={'Authorization': access_token, 'Content-Type': 'application/json'},
        json={'data': {'id': prod_id, 'type': 'cart_item', 'quantity': quantity}}
    )
    response.raise_for_status()


def delete_from_cart(access_token, cart_id, prod_id):
    response = requests.delete(
        f'https://api.moltin.com/v2/carts/{cart_id}/items/{prod_id}',
        headers={'Authorization': access_token}
    )
    response.raise_for_status()


def delete_the_cart(access_token, cart_id):
    response = requests.delete(
        f'https://api.moltin.com/v2/carts/{cart_id}',
        headers={'Authorization': access_token}
    )
    response.raise_for_status()


def get_cart_items(access_token, cart_id):
    return execute_get_request(
        f'https://api.moltin.com/v2/carts/{cart_id}/items',
        headers={'Authorization': access_token}
    )


def get_cart_info(access_token, cart_id):
    cart_info = []
    for cart_item in get_cart_items(access_token, cart_id):
        name, description, quantity, amount = (
            cart_item['name'],
            cart_item['description'],
            cart_item['quantity'],
            cart_item['meta']['display_price']['with_tax']['value']['formatted']
        )
        cart_info.append(f'<b>{name}</b>\n<i>{description}</i>\n{quantity} шт. на сумму: {amount}')
    cart_info.append(get_cart_amount(access_token, cart_id))
    return '\n\n'.join(cart_info)


def get_quantity_product_in_cart(access_token, cart_id, product_id):
    quantity_in_cart = [cart_item['quantity'] for cart_item in get_cart_items(access_token, cart_id) if cart_item['id'] == product_id]
    return quantity_in_cart[0] if quantity_in_cart else 0


def get_cart_amount(access_token, cart_id):
    cart_price = execute_get_request(
        f'https://api.moltin.com/v2/carts/{cart_id}',
        headers={'Authorization': access_token}
    )
    return 'Всего к оплате: %s' % cart_price['meta']['display_price']['with_tax']['formatted']


def get_payment_info(access_token, cart_id):
    cart_info = []
    for cart_item in get_cart_items(access_token, cart_id):
        name, quantity, amount = (
            cart_item['name'],
            cart_item['quantity'],
            cart_item['meta']['display_price']['with_tax']['value']['formatted']
        )
        cart_info.append(f'{name} - {quantity} шт. на сумму: {amount}')
    cart_description = '\n'.join(cart_info)
    cart_price = execute_get_request(
        f'https://api.moltin.com/v2/carts/{cart_id}',
        headers={'Authorization': access_token}
    )
    return (
        cart_description,
        cart_price['meta']['display_price']['with_tax']['currency'],
        cart_price['meta']['display_price']['with_tax']['amount']
    )


def add_new_customer(access_token, email):
    headers = {'Authorization': access_token, 'Content-Type': 'application/json'}
    data = {'data': {'type': 'customer', 'name': email.split('@')[0], 'email': email}}
    response = requests.post(
        'https://api.moltin.com/v2/customers',
        headers=headers,
        json=data
    )
    response.raise_for_status()


def add_new_flow(access_token, flow_name, flow_slug, flow_description):
    headers = {'Authorization': access_token, 'Content-Type': 'application/json'}
    data = {
        'data': {
            'type': 'flow',
            'name': flow_name,
            'slug': flow_slug,
            'description': flow_description,
            'enabled': True
        }
    }
    response = requests.post(
        'https://api.moltin.com/v2/flows',
        headers=headers,
        json=data
    )
    response.raise_for_status()
    return response.json()['data']['id']


def update_flow(access_token, flow_id, flow_name, flow_slug, flow_description):
    headers = {'Authorization': access_token, 'Content-Type': 'application/json'}
    data = {
        'data': {
            'id': flow_id,
            'type': 'flow',
            'name': flow_name,
            'slug': flow_slug,
            'description': flow_description,
            'enabled': True
        }
    }
    response = requests.post(
        f'https://api.moltin.com/v2/flows/{flow_id}',
        headers=headers,
        json=data
    )
    response.raise_for_status()


def add_new_field(access_token, flow_id, field_characteristics):
    headers = {'Authorization': access_token, 'Content-Type': 'application/json'}
    data = {
        'data': {
            'type': 'field',
            'name': field_characteristics['name'],
            'slug': field_characteristics['slug'],
            'description': field_characteristics['description'],
            'field_type': field_characteristics['type'],
            'enabled': True,
            'required': False,
            'relationships': {
                'flow': {
                    'data': {
                        'type': 'flow',
                        'id': flow_id
                    }
                }
            }
        }
    }
    response = requests.post(
        'https://api.moltin.com/v2/fields',
        headers=headers,
        json=data
    )
    response.raise_for_status()
    return response.json()['data']['id']


def add_new_entry(access_token, flow_slug, fields):
    headers = {'Authorization': access_token, 'Content-Type': 'application/json'}
    data = {
        'data': {
            'type': 'entry'
        }
    }
    data['data'].update(fields)
    response = requests.post(
        f'https://api.moltin.com/v2/flows/{flow_slug}/entries',
        headers=headers,
        json=data
    )
    response.raise_for_status()
    return response.json()['data']['id']


def update_entry(access_token, flow_slug, entry_id, fields):
    headers = {'Authorization': access_token, 'Content-Type': 'application/json'}
    data = {
        'data': {
            'type': 'entry'
        }
    }
    data['data'].update(fields)
    response = requests.put(
        f'https://api.moltin.com/v2/flows/{flow_slug}/entries/{entry_id}',
        headers=headers,
        json=data
    )
    response.raise_for_status()


def get_pizzeria_entries(access_token):
    url = f'https://api.moltin.com/v2/flows/pizzeria/entries'
    entries = execute_get_request(
        url,
        {'Authorization': access_token}
    )
    return [{'address': entry['address'], 'longitude': entry['longitude'], 'latitude': entry['latitude']} for entry in entries]


def get_entry(access_token, flow_slug, entry_id):
    url = f'https://api.moltin.com/v2/flows/{flow_slug}/entries/{entry_id}'
    return execute_get_request(
        url,
        {'Authorization': access_token}
    )


def get_customer(access_token, field, value):
    return get_item_id(access_token, 'customers', field=field, value=value)


def get_address(access_token, slug, field, value):
    entry_id = get_item_id(access_token, 'entries', slug=slug, field=field, value=value)
    if entry_id:
        return get_entry(access_token, slug, entry_id)


def read_models_from_file(access_token, file_name):
    models = []
    with open(file_name, 'r') as file_handler:
        models_catalog = json.load(file_handler)

    for model in models_catalog:
        model_ids = {'flow_id': '', 'flow_slug': '', 'fields': {}}
        flow_id = get_item_id(
            access_token, 'flows', field='name',
            value=model['flow']['name']
        )
        if not flow_id:
            flow_id = add_new_flow(
                access_token,
                model['flow']['name'],
                model['flow']['slug'],
                model['flow']['description']
            )
        if flow_id:
            model_ids['flow_id'], model_ids['flow_slug'] = flow_id, model['flow']['slug']
        else:
            models.append(model_ids)
            continue
        for field in model['fields']:
            field_id = get_item_id(
                access_token,
                'fields',
                slug=model['flow']['slug'],
                field='slug',
                value=field['slug']
            )
            if field_id:
                model_ids['fields'][field['name']] = field_id
                continue
            model_ids['fields'][field['name']] = add_new_field(access_token, flow_id, field)
        models.append(model_ids)

    return models


def load_image(access_token, product_id, image_folder, image_url):
    url_path = urlparse(image_url).path
    image_file = url_path.split('/')[-1]

    response = requests.get(image_url)
    response.raise_for_status()

    image_path = os.path.join(image_folder, image_file)
    with open(image_path, 'wb') as file_handler:
        file_handler.write(response.content)
    load_file(access_token, product_id, image_path)


def load_products_from_file(access_token, filename, image_folder):

    with open(filename, 'r') as file_handler:
        products = json.load(file_handler)

    for product in tqdm(products, desc="Загружено", unit="наименований"):
        product_characteristic = {
            'type': 'product',
            'name': product['name'],
            'slug': slugify(product['name']),
            'sku': str(product['id']),
            'description': product['description'],
            'manage_stock': False,
            'price': [
                {
                    'amount': product['price'],
                    'currency': 'RUB',
                    'includes_tax': True
                }
            ],
            'status': 'live',
            'commodity_type': 'physical'
        }
        product_id = get_item_id(
            access_token, 'products',
            field='sku', value=str(product['id'])
        )
        if product_id:
            update_product(access_token, product_id, product_characteristic)
        else:
            product_id = add_new_product(access_token, product_characteristic)
        if product['product_image']['url']:
            load_image(access_token, product_id, image_folder, product['product_image']['url'])


def load_categories_from_file(access_token, filename):

    with open(filename, 'r') as file_handler:
        categories = json.load(file_handler)

    for category in tqdm(categories, desc="Загружено", unit="категорий"):
        category_characteristic = {
            'type': 'category',
            'name': category['name'],
            'slug': slugify(category['name']),
            'description': category['description'],
            'status': 'live'
        }
        category_id = get_item_id(
            access_token, 'categories',
            field='name', value=category['name']
        )
        if category_id:
            update_category(access_token, category_id, category_characteristic)
        else:
            category_id = add_new_category(access_token, category_characteristic)


def load_addresses_from_file(access_token, filename, pizzeria_model):

    with open(filename, 'r') as file_handler:
        addresses = json.load(file_handler)

    for address in tqdm(addresses, desc="Загружено", unit="адресов"):
        save_address(
            access_token,
            pizzeria_model['flow_slug'],
            'address',
            address['address']['full'],
            address={
                'address': address['address']['full'],
                'alias': address['alias'],
                'longitude': address['coordinates']['lon'],
                'latitude': address['coordinates']['lat']
            }
        )


def save_address(access_token, slug, field, value, address):
    entry_id = get_item_id(access_token, 'entries', slug=slug, field=field, value=value)
    if entry_id:
        update_entry(access_token, slug, entry_id, address)
    else:
        add_new_entry(access_token, slug, address)


def create_order(access_token, chat_id):
    headers = {'Authorization': access_token, 'Content-Type': 'application/json'}
    customer_address = get_address(access_token, 'customeraddress', 'customerid', str(chat_id))
    customer_id = get_customer(access_token, 'email', customer_address['email'])
    customer_info = execute_get_request(
        f'https://api.moltin.com/v2/customers/{customer_id}',
        {'Authorization': access_token}
    )
    data = {
        'data': {
            'customer': {
                'id': customer_id
            },
            'billing_address': {
                'first_name': customer_info['name'],
                'last_name': customer_info['name'],
                'line_1': customer_address['address'],
                'city': customer_address['city'],
                'postcode': '0000',
                'county': customer_address['county'],
                'country': customer_address['country']
            },
            'shipping_address': {
                'first_name': customer_info['name'],
                'last_name': customer_info['name'],
                'phone_number': customer_address['telephone'],
                'line_1': customer_address['address'],
                'postcode': '0000',
                'county': customer_address['county'],
                'country': customer_address['country']
            }
        }
    }
    response = requests.post(
        f'https://api.moltin.com/v2/carts/{chat_id}/checkout',
        headers=headers,
        json=data
    )
    response.raise_for_status()
    return response.json()['data']['id']


def set_order_payment(access_token, order_id):
    headers = {'Authorization': access_token, 'Content-Type': 'application/json'}
    data = {
        'data': {
            'gateway': 'manual',
            'method': 'authorize'
        }
    }
    response = requests.post(
        f'https://api.moltin.com/v2/orders/{order_id}/payments',
        headers=headers,
        json=data
    )
    response.raise_for_status()
    return response.json()['data']['id']


def confirm_order_payment(access_token, order_id, transaction_id):
    headers = {'Authorization': access_token, 'Content-Type': 'application/json'}
    data = {
        'data': {
            'gateway': 'manual',
            'method': 'capture'
        }
    }
    response = requests.post(
        f'https://api.moltin.com/v2/orders/{order_id}/transactions/{transaction_id}/capture',
        headers=headers,
        json=data
    )
    response.raise_for_status()


def confirm_order_shipping(access_token, order_id):
    if not order_id:
        return
    headers = {'Authorization': access_token, 'Content-Type': 'application/json'}
    data = {
        'data': {
            'type': 'order',
            'shipping': 'fulfilled'
        }
    }
    response = requests.put(
        f'https://api.moltin.com/v2/orders/{order_id}',
        headers=headers,
        json=data
    )
    response.raise_for_status()
