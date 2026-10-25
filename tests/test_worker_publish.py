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

    def test_youtube_addition_retains_old_secrets_and_creates_only_its_sqlite_class(self):
        settings = {'compatibility_date': '2026-09-28', 'bindings': [
            {'name': 'SUBS', 'type': 'kv_namespace', 'namespace_id': 'same'},
            {'name': 'YT_REFRESH_TOKEN', 'type': 'secret_text'}]}
        result = publish.upload_metadata(settings, True)
        self.assertEqual(result['keep_bindings'], ['kv_namespace', 'secret_text'])
        self.assertEqual(result['bindings'], [{'name': 'YT_PUBLISHER', 'type': 'durable_object_namespace', 'class_name': 'YouTubePublisher'}])
        self.assertEqual(result['migrations']['new_sqlite_classes'], ['YouTubePublisher'])
        settings['bindings'] += result['bindings']
        repeated = publish.upload_metadata(settings, True)
        self.assertNotIn('migrations', repeated)
        self.assertEqual(repeated['bindings'], [])

    def test_unknown_existing_durable_object_state_is_not_overwritten(self):
        with self.assertRaises(RuntimeError):
            publish.upload_metadata({'compatibility_date': '2026-09-28', 'bindings': [
                {'name': 'YT_PUBLISHER', 'type': 'durable_object_namespace', 'class_name': 'OtherClass'}]}, True)
