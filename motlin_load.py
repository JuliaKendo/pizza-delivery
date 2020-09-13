import os
import re
import json
import argparse
import requests
import motlin_lib
import motlin_models
from tqdm import tqdm
from dotenv import load_dotenv
from urllib.parse import urlparse

TEMPORARY_IMAGE_FOLDER = 'images'


def generate_slug(product_name):
    symbols = (u"абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ",
               u"abvgdeejzijklmnoprstufhzcss_y_euaABVGDEEJZIJKLMNOPRSTUFHZCSS_Y_EUA")

    name = ''.join(re.findall('[a-z]+|[а-я]+|[0-9]+', product_name.lower()))
    return name.translate({ord(a): ord(b) for a, b in zip(*symbols)})


def load_image(motlin_token, product_id, url_image):
    url_path = urlparse(url_image).path
    image_file = url_path.split('/')[-1]

    response = requests.get(url_image)
    response.raise_for_status()

    image_path = os.path.join(TEMPORARY_IMAGE_FOLDER, image_file)
    with open(image_path, 'wb') as file_handler:
        file_handler.write(response.content)
    motlin_lib.load_file(motlin_token, product_id, image_path)


def load_products(motlin_token, filename):

    with open(filename, 'r') as file_handler:
        products = json.load(file_handler)

    for product in tqdm(products, desc="Загружено", unit="наименований"):
        product_characteristic = {
            'type': 'product',
            'name': product['name'],
            'slug': generate_slug(product['name']),
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
        product_id = motlin_lib.get_item_id(
            motlin_token,
            'products',
            field='sku',
            value=str(product['id'])
        )
        if product_id:
            motlin_lib.update_product(motlin_token, product_id, product_characteristic)
        else:
            product_id = motlin_lib.add_new_product(motlin_token, product_characteristic)
        if product['product_image']['url']:
            load_image(motlin_token, product_id, product['product_image']['url'])


def load_addresses(motlin_token, filename, pizzeria_model):

    with open(filename, 'r') as file_handler:
        addresses = json.load(file_handler)

    for address in tqdm(addresses, desc="Загружено", unit="адресов"):
        fields = {
            'address': address['address']['full'],
            'alias': address['alias'],
            'longitude': address['coordinates']['lon'],
            'latitude': address['coordinates']['lat']
        }
        entry_id = motlin_lib.get_item_id(
            motlin_token,
            'entries',
            slug=pizzeria_model['flow_slug'],
            field='address',
            value=address['address']['full']
        )
        if entry_id:
            motlin_lib.update_entry(motlin_token, pizzeria_model['flow_slug'], entry_id, fields)
        else:
            motlin_lib.add_new_entry(motlin_token, pizzeria_model['flow_slug'], fields)


def create_parser():
    parser = argparse.ArgumentParser(description='Параметры запуска скрипта')
    parser.add_argument('-m', '--models', default='models.json', help='Путь к *.json файлу с описанием моделей')
    parser.add_argument('-p', '--products', default='', help='Путь к *.json файлу с продуктами который необходимо загрузить')
    parser.add_argument('-a', '--address', default='', help='Путь к *.json файлу с адресами который необходимо загрузить')
    return parser


def main():
    load_dotenv()
    motlin_token, token_expires = motlin_lib.get_moltin_access_token(
        client_secret=os.getenv('MOLTIN_CLIENT_SECRET'),
        client_id=os.getenv('MOLTIN_CLIENT_ID')
    )

    parser = create_parser()
    args = parser.parse_args()
    os.makedirs(TEMPORARY_IMAGE_FOLDER, exist_ok=True)

    try:
        models = motlin_models.get_models(motlin_token, args.models)
        if args.products:
            load_products(motlin_token, args.products)
        if args.address:
            pizzeria_model = [model for model in models if model['flow_slug'] == 'pizzeria'][0]
            load_addresses(motlin_token, args.address, pizzeria_model)
    except OSError as error:
        print(f'Ошибка загрузки файла: {error}')
    except (KeyError, TypeError, ValueError) as error:
        print(f'Ошибка загрузки данных из файла: {error}')
    except requests.exceptions.ConnectionError:
        print('Отсутствует подключение к интернету')
    except requests.exceptions.HTTPError:
        print('Ошибка записи данных на сайт Motlin')
    finally:
        for root, dirs, files in os.walk(TEMPORARY_IMAGE_FOLDER, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(TEMPORARY_IMAGE_FOLDER)


if __name__ == "__main__":
    main()
