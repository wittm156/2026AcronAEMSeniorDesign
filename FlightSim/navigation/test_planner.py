"""This is an AI generated test file for finding bugs with Ollama responses. None of this was writen by me"""
import json
import unittest
from copy import deepcopy
from io import BytesIO
from unittest.mock import patch
from navigation.planner import distance_nm, plan_route
from navigation.query_model import OllamaQueryModel

class RouteTests(unittest.TestCase):
    def setUp(self):
        self.points = [{'id': 'A', 'lat': 0, 'lon': 0},
                       {'id': 'WP-1', 'lat': 0, 'lon': 0.03},
                       {'id': 'B', 'lat': 0, 'lon': 0.1}]
        self.database = {'origin': 'A', 'airports': [self.points[0], self.points[-1]]}
        self.intent = {'destination_id': 'B', 'optimization': 'distance'}

    def test_python_distances_preserve_model_coordinates(self):
        original = deepcopy(self.points)
        result = plan_route(self.database, {**self.intent, 'waypoints': self.points})['selected']
        self.assertEqual(self.points, original)
        self.assertAlmostEqual(result['distance_nm'], 6.004046, places=5)
        self.assertEqual(result['waypoints'][-1]['distance_from_start_nm'], result['distance_nm'])
        for actual, expected in zip(result['waypoints'], original):
            self.assertEqual((actual['lat'], actual['lon']), (expected['lat'], expected['lon']))
            self.assertEqual(actual['altitude_ft'], 1500)

    def test_invalid_geometry_is_rejected(self):
        for change in ('missing', 'endpoint', 'spacing', 'nan'):
            points = deepcopy(self.points)
            if change == 'missing':
                points = []
            elif change == 'endpoint':
                points[-1]['lat'] = 0.1
            elif change == 'spacing':
                points = [points[0], points[-1]]
            else:
                points[1]['lat'] = float('nan')
            with self.subTest(change=change), self.assertRaises(ValueError):
                plan_route(self.database, {**self.intent, 'waypoints': points})

    @patch('navigation.query_model.urlopen')
    def test_requests_pass_python_distance_without_tools(self, urlopen):
        messages = [self.intent, {'waypoints': {p['id']: {'lat': p['lat'], 'lon': p['lon']} for p in self.points}}]
        urlopen.side_effect = [BytesIO(json.dumps({'message': {'content': json.dumps(m)}}).encode()) for m in messages]
        result = OllamaQueryModel().parse('Go to B', self.database)
        self.assertEqual(result['destination'], 'B')
        requests = [json.loads(c.args[0].data) for c in urlopen.call_args_list]
        self.assertEqual(len(requests), 2)
        self.assertTrue(all('tools' not in request for request in requests))
        self.assertIn(f'{distance_nm(self.points[0], self.points[-1]):.9f}', requests[1]['messages'][0]['content'])
        entries = requests[1]['format']['properties']['waypoints']
        self.assertEqual(entries['required'], ['A', 'WP-1', 'B'])
        self.assertEqual(entries['properties']['B']['properties']['lon']['enum'], [0.1])

    @patch.object(OllamaQueryModel, '_chat')
    def test_one_bounded_coordinate_correction(self, chat):
        chat.side_effect = [self.intent, {'waypoints': [self.points[0], self.points[-1]]}, {'waypoints': self.points}]
        result = OllamaQueryModel().parse('Go to B', self.database)
        self.assertEqual(len(result['selected']['waypoints']), 3)
        self.assertEqual(chat.call_count, 3)

if __name__ == '__main__':
    unittest.main()
