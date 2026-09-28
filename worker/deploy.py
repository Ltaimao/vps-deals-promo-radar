#!/usr/bin/env python3
"""Deploy the vpsdealswire-api worker via the Cloudflare API (multipart upload).
Uses the skill's surrogate credential mechanism — never touches the raw token."""
import json, sys, urllib.request

sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
from dynamic_credentials import add_surrogate_to_request, read_json_response

ACCOUNT = "41adaf2bce076e1cefb1a8ad67b51856"
SCRIPT = "vpsdealswire-api"
KV_ID = "4d8d62c95b204b4e9eeb5aa5e6c77351"

with open(sys.argv[1], "rb") as fh:
    script_bytes = fh.read()

metadata = {
    "main_module": "api.js",
    "compatibility_date": "2026-09-28",
    "bindings": [
        {"type": "kv_namespace", "name": "SUBS", "namespace_id": KV_ID},
        {"type": "send_email", "name": "EMAIL"},
    ],
}

boundary = "----vpsdw-deploy-boundary"
body = b""
body += ("--" + boundary + '\r\nContent-Disposition: form-data; name="metadata"\r\n'
         "Content-Type: application/json\r\n\r\n").encode()
body += json.dumps(metadata).encode() + b"\r\n"
body += ("--" + boundary + '\r\nContent-Disposition: form-data; name="api.js"; filename="api.js"\r\n'
         "Content-Type: application/javascript+module\r\n\r\n").encode()
body += script_bytes + b"\r\n"
body += ("--" + boundary + "--\r\n").encode()

url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/workers/scripts/{SCRIPT}"
req = urllib.request.Request(url, data=body, method="PUT")
req.add_header("Content-Type", "multipart/form-data; boundary=" + boundary)
add_surrogate_to_request(req, "custom.cloudflare", allowed_hosts=["api.cloudflare.com"])
resp = read_json_response(urllib.request.urlopen(req))
print(json.dumps(resp, indent=2)[:2000])
sys.exit(0 if resp.get("success") else 1)
