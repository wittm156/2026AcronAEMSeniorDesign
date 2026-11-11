"""Ask Ollama for waypoint coordinates using distances calculated in Python.
Coded with debugging help from ollama server when things went wrong as it
automatically outputs corrections for syntax and edge case errors"""
import json
from math import ceil
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from navigation.planner import distance_nm, plan_route, WAYPOINT_SPACING_NM, ROUTE_ALTITUDE_FT


class OllamaQueryModel:
    def __init__(self, model='qwen3:4b', endpoint='http://127.0.0.1:11434/api/chat'):
        self.model = model
        self.endpoint = endpoint

    def _chat(self, messages, schema):
        payload = {'model': self.model, 'stream': False, 'format': schema,
                   'options': {'temperature': 0}, 'messages': messages}
        request = Request(self.endpoint, data=json.dumps(payload).encode('utf-8'),
                          headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urlopen(request, timeout=180) as response:
                result = json.load(response)
        except HTTPError as error:
            raise ValueError(f'Ollama HTTP {error.code}: {error.read().decode("utf-8", errors="replace")}') from error
        try:
            return json.loads(result['message']['content'])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError('Ollama did not return valid route JSON.') from error

    def parse(self, text, database):
        if not text.strip():
            raise ValueError('Enter a destination first.')
        intent_schema = {'type': 'object', 'properties': {
            'destination_id': {'type': 'string', 'enum': [a['id'] for a in database['airports']] + ['UNKNOWN']},
            'optimization': {'type': 'string', 'enum': ['distance', 'unsupported']}},
            'required': ['destination_id', 'optimization'], 'additionalProperties': False}
        intent = self._chat([
            {'role': 'system', 'content': 'Extract destination and preference only. Default to distance. '
             'Use unsupported for time, battery or energy. Use UNKNOWN for missing or ambiguous destinations. '
             'Airports: ' + json.dumps(database['airports'])},
            {'role': 'user', 'content': text}], intent_schema)
        airports = {a['id']: a for a in database['airports']}

        """Test edge cases"""
        if not isinstance(intent, dict) or not isinstance(intent.get('destination_id'), str) or intent['destination_id'] not in airports:
            raise ValueError('Destination unclear or unavailable. Use an airport name or ID.')
        if intent.get('optimization') != 'distance':
            raise ValueError('Only shortest distance is supported.')
        start, end = airports[database['origin']], airports[intent['destination_id']]
        if start['id'] == end['id']:
            raise ValueError('Destination is the current origin. Choose another airport.')


        total = distance_nm(start, end) #IMPORTANT distance calculation line not done by ollama
        segments = max(1, ceil(total / (WAYPOINT_SPACING_NM * 0.8))) #rough segment calculation check
        if segments + 1 > 2000:
            raise ValueError('Route exceeds the 2000-waypoint limit.')
        point_schemas = []
        for index in range(segments + 1):
            airport = start if index == 0 else end if index == segments else None
            properties = {
                'id': {'type': 'string', 'enum': [airport['id'] if airport else f'WP-{index}']},
                'lat': {'type': 'number', 'enum': [airport['lat']]} if airport else {'type': 'number', 'minimum': -90, 'maximum': 90},
                'lon': {'type': 'number', 'enum': [airport['lon']]} if airport else {'type': 'number', 'minimum': -180, 'maximum': 180}}
            point_schemas.append({'type': 'object', 'properties': properties,
                                  'required': ['id', 'lat', 'lon'], 'additionalProperties': False})
        # Named entries work with Ollama's schema converter without depending on
        # tuple-array support. Python only orders and labels returned coordinates.
        named_points = {}
        for point_schema in point_schemas:
            identifier = point_schema['properties'].pop('id')['enum'][0]
            point_schema['required'] = ['lat', 'lon']
            named_points[identifier] = point_schema
        schema = {'type': 'object', 'properties': {'waypoints': {
            'type': 'object', 'properties': named_points, 'required': list(named_points),
            'additionalProperties': False}},
            'required': ['waypoints'], 'additionalProperties': False}
        messages = [{'role': 'system', 'content':
            'Generate coordinates for a direct great-circle route. Python has already calculated '
            'the distance; do not calculate or return distances. Return only the waypoints JSON. '
            f'Origin: {json.dumps(start)}. Destination: {json.dumps(end)}. '
            f'Direct distance: {total:.9f} NM. Maximum leg length: {WAYPOINT_SPACING_NM:g} NM. '
            f'Return exactly {segments + 1} points including both endpoints, evenly spaced along '
            f'the route (target leg length {total / segments:.6f} NM). '
            'Return waypoints as an object keyed by these IDs in order: '
            + json.dumps(list(named_points)) + '. Each value contains lat and lon. '
            'Copy exact endpoint coordinates. Create every intermediate latitude and longitude yourself.'},
            {'role': 'user', 'content': text}]
        print(f'[Route distance] Python: {total:.3f} NM; requesting {segments + 1} waypoints from Ollama.', flush=True)

        """Calls chat function and actually parses into Ollama, everything before if setup for this part"""
        for attempt in range(2):
            response = self._chat(messages, schema)
            try:
                if not isinstance(response, dict):
                    raise ValueError('Ollama must return a waypoints object.')
                points = response.get('waypoints')
                if isinstance(points, dict):
                    if set(points) != set(named_points):
                        raise ValueError('Ollama did not return the required waypoint entries.')
                    points = [dict(points[identifier], id=identifier) for identifier in named_points]
                return plan_route(database, {**intent, 'waypoints': points})
            except ValueError as error:
                if attempt:
                    raise ValueError(f'Ollama waypoints rejected: {error}') from error
                print(f'[Ollama validation] {error}; requesting one correction.', flush=True)
                messages.extend([{'role': 'assistant', 'content': json.dumps(response)},
                                 {'role': 'user', 'content': f'Correct these coordinates: {error}. '
                                  'Return the full waypoint list with evenly spaced intermediate points.'}])
