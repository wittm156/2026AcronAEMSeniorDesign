"""Validate and package Ollama routes. Calculaes the distance which is parsed into Ollama."""
from copy import deepcopy
from math import asin, cos, isfinite, radians, sin, sqrt

WAYPOINT_SPACING_NM = 5
ROUTE_ALTITUDE_FT = 1500.0
EARTH_RADIUS_NM = 3440.065
# Only allow floating-point representation noise, not rounded airport positions.
ENDPOINT_COORDINATE_TOLERANCE_DEG = 1e-9


def distance_nm(start, end):
    """Calculates great-circle distance in nautical miles."""
    lat1, lat2 = radians(start['lat']), radians(end['lat'])
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin(radians(end['lon'] - start['lon']) / 2) ** 2
    return EARTH_RADIUS_NM * 2 * asin(sqrt(min(1.0, max(0.0, a))))


def _number(value):
    """valid number check helper function"""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError('Ollama route contains a missing or invalid numeric field.')
    return value


def plan_route(database, model_route):
    """Preserve Ollama coordinates; calculate distances and add altitude in Python."""
    if not isinstance(model_route, dict):
        raise ValueError('Ollama must return a route object.')
    airports = {a['id']: a for a in database['airports']}
    destination = model_route.get('destination_id')

    """checks start"""
    if not isinstance(destination, str) or destination not in airports:
        raise ValueError('Destination unclear or unavailable. Use an airport name or ID.')
    if model_route.get('optimization') != 'distance':
        raise ValueError('Only shortest distance is supported.')
    origin = database['origin']
    if destination == origin:
        raise ValueError('Destination is the current origin. Choose another airport.')
    points = model_route.get('waypoints')
    if not isinstance(points, list) or not 2 <= len(points) <= 2000:
        raise ValueError('Ollama must return between 2 and 2000 waypoints.')
    ids = set()
    for p in points:
        if not isinstance(p, dict):
            raise ValueError('Ollama returned an invalid waypoint.')
        identifier = p.get('id')
        if not isinstance(identifier, str) or not identifier.strip() or identifier in ids:
            raise ValueError('Waypoint IDs must be nonempty and unique.')
        ids.add(identifier)
        if not -90 <= _number(p.get('lat')) <= 90 or not -180 <= _number(p.get('lon')) <= 180:
            raise ValueError('Waypoint coordinates are out of range.')
    """checks end"""

    """check for endpoint"""
    for p, airport_id in ((points[0], origin), (points[-1], destination)):
        airport = airports[airport_id]
        tolerance = ENDPOINT_COORDINATE_TOLERANCE_DEG
        longitude_error = abs((p['lon'] - airport['lon'] + 180) % 360 - 180)
        if (p['id'] != airport_id or abs(p['lat'] - airport['lat']) > tolerance + 1e-12
                or longitude_error > tolerance + 1e-12):
            raise ValueError(f'Ollama endpoint {airport_id} must have lat={airport["lat"]}, '
                             f'lon={airport["lon"]} (coordinate tolerance {tolerance:g} degrees); '
                             f'received id={p["id"]}, '
                             f'lat={p["lat"]}, lon={p["lon"]}.')
    measured = 0.0
    waypoints = deepcopy(points)
    waypoints[0]['distance_from_start_nm'] = 0.0
    for index, (start, end) in enumerate(zip(points, points[1:]), 1):
        leg = distance_nm(start, end)
        if leg > WAYPOINT_SPACING_NM + 0.05:
            raise ValueError(f'Ollama leg {start["id"]} -> {end["id"]} is {leg:.3f} NM; '
                             f'maximum spacing is {WAYPOINT_SPACING_NM:g} NM (0.05 NM tolerance).')
        measured += leg
        waypoints[index]['distance_from_start_nm'] = measured

    """check for total route length"""
    direct = distance_nm(airports[origin], airports[destination])
    if measured > direct + max(0.1, direct * 0.02):
        raise ValueError('Ollama route deviates from the requested direct shortest route.')
    for point in waypoints:
        point['altitude_ft'] = ROUTE_ALTITUDE_FT
    route = {'id': 'OLLAMA', 'points': [p['id'] for p in waypoints],
             'distance_nm': measured, 'waypoints': waypoints,
             'waypoint_spacing_nm': WAYPOINT_SPACING_NM, 'altitude_reference': 'MSL',
             'geometry': {'type': 'LineString', 'coordinates': [[p['lon'], p['lat']] for p in waypoints]}}
    return {'origin': origin, 'destination': destination, 'selected': route, 'alternatives': [route]}

