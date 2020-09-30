import requests
from geopy import distance


def fetch_coordinates(apikey, place):
    base_url = "https://geocode-maps.yandex.ru/1.x"
    params = {"geocode": place, "apikey": apikey, "format": "json"}
    response = requests.get(base_url, params=params)
    response.raise_for_status()
    places_found = response.json()['response']['GeoObjectCollection']['featureMember']
    if places_found:
        most_relevant = places_found[0]
        lon, lat = most_relevant['GeoObject']['Point']['pos'].split(" ")
        return float(lon), float(lat)
    else:
        return None, None


def fetch_address(apikey, longitude, latitude):
    base_url = "https://geocode-maps.yandex.ru/1.x"
    params = {"geocode": f'{longitude},{latitude}', "apikey": apikey, "format": "json"}
    response = requests.get(base_url, params=params)
    response.raise_for_status()
    places_found = response.json()['response']['GeoObjectCollection']['featureMember']
    if places_found:
        most_relevant = places_found[0]
        return most_relevant['GeoObject']['name']


def fetch_address_decryption(apikey, longitude, latitude):
    address_decryption = {'CountryName': '-', 'AdministrativeAreaName': '-', 'LocalityName': '-'}
    base_url = "https://geocode-maps.yandex.ru/1.x"
    params = {"geocode": f'{longitude},{latitude}', "apikey": apikey, "format": "json"}
    response = requests.get(base_url, params=params)
    response.raise_for_status()

    places_found = response.json()['response']['GeoObjectCollection']['featureMember']
    if not places_found:
        return address_decryption

    for key, value in get_value(places_found[0]):
        if key not in address_decryption.keys():
            continue
        address_decryption[key] = value

    return address_decryption


def calculate_distance(addresses, longitude, latitude):
    for address in addresses:
        address['distance'] = distance.distance((longitude, latitude), (address['longitude'], address['latitude'])).km


def get_value(address_structure):
    for key, value in address_structure.items():
        if type(value) is dict:
            yield from get_value(value)
        else:
            yield key, value
