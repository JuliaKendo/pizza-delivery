import os
import argparse
import requests
from libs import motlin_lib
from dotenv import load_dotenv

TEMPORARY_IMAGE_FOLDER = 'images'


def create_parser():
    parser = argparse.ArgumentParser(description='Параметры запуска скрипта')
    parser.add_argument('-m', '--models', default='models.json', help='Путь к *.json файлу с описанием моделей')
    parser.add_argument('-с', '--categories', default='', help='Путь к *.json файлу с категориями продуктов')
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
        models = motlin_lib.read_models_from_file(motlin_token, args.models)
        if args.categories:
            motlin_lib.load_categories_from_file(motlin_token, args.categories)
        if args.products:
            motlin_lib.load_products_from_file(motlin_token, args.products, TEMPORARY_IMAGE_FOLDER)
        if args.address:
            pizzeria_model = [model for model in models if model['flow_slug'] == 'pizzeria'][0]
            motlin_lib.load_addresses_from_file(motlin_token, args.address, pizzeria_model)
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
