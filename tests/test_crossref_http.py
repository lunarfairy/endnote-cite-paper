import http.client
import importlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


class Response:
    def __init__(self, body, incomplete=False):
        self.body, self.incomplete = body, incomplete
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self):
        if self.incomplete:
            raise http.client.IncompleteRead(self.body)
        return self.body


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.http = importlib.import_module('crossref_http')
        self.body = json.dumps({'message': {'DOI': '10.1234/test'}}).encode()

    def test_complete_json_in_incomplete_read(self):
        audit = []
        with patch.object(self.http.urllib.request, 'urlopen', return_value=Response(self.body, True)):
            data = self.http.fetch_json('https://example.invalid', audit=audit)
        self.assertEqual(data['message']['DOI'], '10.1234/test')
        self.assertTrue(audit)

    def test_invalid_partial_json_retries_bounded(self):
        with patch.object(self.http.urllib.request, 'urlopen', return_value=Response(b'{"message":', True)) as request:
            with self.assertRaises(ValueError):
                self.http.fetch_json('https://example.invalid', attempts=2)
        self.assertEqual(request.call_count, 2)

    def test_invalid_message_shape_rejected(self):
        with patch.object(self.http.urllib.request, 'urlopen', return_value=Response(b'{"message": []}')):
            with self.assertRaises(ValueError):
                self.http.fetch_json('https://example.invalid', attempts=1)


if __name__ == '__main__':
    unittest.main()
