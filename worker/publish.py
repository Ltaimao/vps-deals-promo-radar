#!/usr/bin/env python3
"""Guarded Worker release using existing CI credentials; never prints values.

The live module must equal the reviewed predecessor or the desired module.
Bindings use the same keep_bindings mechanism as Wrangler's upload metadata.
Only the script endpoint is written; schedules/routes are never mutated.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from email import policy
from email.parser import BytesParser
from pathlib import Path

SCRIPT = 'vpsdealswire-api'
ROOT = Path(__file__).resolve().parent.parent


def module_bytes(content_type, body):
    if content_type.startswith('multipart/'):
        message = BytesParser(policy=policy.default).parsebytes(
            b'Content-Type: ' + content_type.encode() + b'\r\nMIME-Version: 1.0\r\n\r\n' + body)
        parts = {p.get_param('name', header='content-disposition') or p.get_filename(): p.get_payload(decode=True)
                 for p in message.iter_parts()}
        modules = {name: data for name, data in parts.items() if name != 'metadata'}
        if set(modules) != {'api.js'}:
            raise RuntimeError('Live Worker is not the reviewed single api.js module; no upload permitted')
        return modules['api.js']
    if 'javascript' in content_type:
        return body
    raise RuntimeError('Unexpected script content type; no upload permitted')


def upload_metadata(settings):
    allowed = ('compatibility_date', 'compatibility_flags', 'logpush', 'placement',
               'tail_consumers', 'streaming_tail_consumers', 'limits', 'observability')
    result = {key: settings[key] for key in allowed if key in settings and settings[key] is not None}
    result.update(main_module='api.js', bindings=[],
                  keep_bindings=sorted({b['type'] for b in settings.get('bindings', [])}))
    if not result.get('compatibility_date'):
        raise RuntimeError('No existing compatibility date; no upload permitted')
    return result


def multipart(metadata, source):
    boundary = '----vps-reviewed-worker-release'
    body = ('--' + boundary + '\r\nContent-Disposition: form-data; name="metadata"\r\n'
            'Content-Type: application/json\r\n\r\n').encode() + json.dumps(metadata).encode() + b'\r\n'
    body += ('--' + boundary + '\r\nContent-Disposition: form-data; name="api.js"; filename="api.js"\r\n'
             'Content-Type: application/javascript+module\r\n\r\n').encode() + source + b'\r\n'
    body += ('--' + boundary + '--\r\n').encode()
    return 'multipart/form-data; boundary=' + boundary, body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('inspect', 'deploy'), default='inspect')
    parser.add_argument('--expected-ref', required=True)
    args = parser.parse_args()
    token = os.environ.get('CLOUDFLARE_API_TOKEN')
    account = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
    if not token or not account:
        raise RuntimeError('Existing CI Cloudflare bindings are unavailable; no upload performed')
    base = 'https://api.cloudflare.com/client/v4/accounts/' + account + '/workers/scripts/' + SCRIPT

    def request(path='', method='GET', body=None, content_type=None):
        headers = {'Authorization': 'Bearer ' + token, 'User-Agent': 'VPS-Deals-Wire-reviewed-release'}
        if content_type:
            headers['Content-Type'] = content_type
        req = urllib.request.Request(base + path, headers=headers, data=body, method=method)
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                data = response.read()
                return response.headers.get('Content-Type', ''), data
        except urllib.error.HTTPError as error:
            raise RuntimeError('Cloudflare ' + method + ' ' + (path or '/script') + ' returned HTTP ' + str(error.code)) from None

    def obj(path):
        _, body = request(path)
        parsed = json.loads(body)
        if not parsed.get('success'):
            raise RuntimeError('Cloudflare read was unsuccessful: ' + path)
        return parsed['result']

    settings = obj('/settings')
    schedules = obj('/schedules')
    source = module_bytes(*request())
    expected = subprocess.check_output(['git', 'show', args.expected_ref + ':worker/api.js'], cwd=ROOT)
    desired = (ROOT / 'worker/api.js').read_bytes()
    sha = lambda value: hashlib.sha256(value).hexdigest()
    summary = {'script': SCRIPT, 'mode': args.mode,
               'live_sha256': sha(source), 'expected_sha256': sha(expected),
               'desired_sha256': sha(desired),
               'binding_names_types': sorted((b['name'], b['type']) for b in settings.get('bindings', [])),
               'cron': [s['cron'] for s in schedules.get('schedules', [])]}
    print(json.dumps(summary), flush=True)
    if source not in (expected, desired):
        raise RuntimeError('Live source differs from reviewed predecessor and target; no upload performed')
    metadata = upload_metadata(settings)
    if args.mode == 'inspect':
        print('INSPECTION PASSED; no writes performed')
        return
    if source == desired:
        print('Already deployed; no writes needed')
        return
    # Recheck for concurrent edits immediately before writing.
    if module_bytes(*request()) != source or obj('/settings') != settings:
        raise RuntimeError('Live source/settings changed during review; no upload performed')
    content_type, body = multipart(metadata, desired)
    _, result = request(method='PUT', body=body, content_type=content_type)
    if not json.loads(result).get('success'):
        raise RuntimeError('Cloudflare upload did not report success')
    if module_bytes(*request()) != desired:
        raise RuntimeError('Post-release source verification failed')
    after = obj('/settings')
    # Compare all binding metadata in memory; no values are logged.
    binding_key = lambda items: sorted(json.dumps(b, sort_keys=True) for b in items)
    if binding_key(after.get('bindings', [])) != binding_key(settings.get('bindings', [])):
        raise RuntimeError('Post-release binding metadata differs; review required')
    if obj('/schedules') != schedules:
        raise RuntimeError('Post-release schedules differ; review required')
    print('DEPLOYMENT VERIFIED: source matches; binding metadata and schedules preserved')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
