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


def calculate_distance(addresses, longitude, latitude):
    for address in addresses:
        address['distance'] = distance.distance((longitude, latitude), (address['longitude'], address['latitude'])).km
