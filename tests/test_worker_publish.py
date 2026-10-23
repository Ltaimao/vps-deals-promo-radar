"""Deployment payload checks; no credentials, network, or actual publishing."""
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('worker_publish', Path(__file__).resolve().parents[1] / 'worker/publish.py')
publish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish)


class PublishTests(unittest.TestCase):
    def test_preserves_binding_types_without_copying_secret_values(self):
        result = publish.upload_metadata({'compatibility_date': '2026-09-28', 'bindings': [
            {'name': 'SUBS', 'type': 'kv_namespace', 'namespace_id': 'namespace'},
            {'name': 'API_KEY', 'type': 'secret_text'},
            {'name': 'CONFIG', 'type': 'plain_text', 'text': 'not-logged'}]})
        self.assertEqual(result['keep_bindings'], ['kv_namespace', 'plain_text', 'secret_text'])
        self.assertEqual(result['bindings'], [])
        self.assertNotIn('not-logged', str(result))

    def test_single_module_round_trip(self):
        ctype, body = publish.multipart({'main_module': 'api.js'}, b'export default {};')
        self.assertEqual(publish.module_bytes(ctype, body), b'export default {};')

    def test_non_module_response_is_rejected(self):
        with self.assertRaises(RuntimeError):
            publish.module_bytes('text/html', b'<html>denied</html>')
