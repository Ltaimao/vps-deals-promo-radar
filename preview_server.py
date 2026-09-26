#!/usr/bin/env python3
# ILANG
# TYPE script
# PROJECT vps-deals-promo-radar
# ROLE 本地预览：按 Cloudflare Pages 的语义回状态码
#       1) site/_redirects 命中 -> 301 + Location
#       2) 静态文件存在 -> 200
#       3) 都不命中 -> 用 site/404.html 当响应体，回 404
#       用来在推线上之前先把状态码跑出来看
# BOUNDARY never:拿 200 兜底不存在的路径|scope:permanent
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 必须走系统 MIME 表：之前只硬编码了 .css/.xml/.txt，.svg 被当成 text/html 发出去，
# 浏览器拒绝把 text/html 当图片解码，于是所有 SVG logo 在本地预览里都是 0x0 的坏图 ——
# 线上 Cloudflare 回的是 image/svg+xml，一切正常。这个假警报害我排查了半天。
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/avif", ".avif")
mimetypes.add_type("application/manifest+json", ".webmanifest")

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(ROOT, "site")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8788


def load_redirects():
    rules = {}
    p = os.path.join(SITE, "_redirects")
    if not os.path.exists(p):
        return rules
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                code = parts[2] if len(parts) > 2 else "301"
                rules[parts[0]] = (parts[1], code)
    return rules


RULES = load_redirects()


class H(BaseHTTPRequestHandler):
    server_version = "pages-preview/1.0"

    def log_message(self, fmt, *a):
        pass

    def do_HEAD(self):
        self.handle_req(head=True)

    def do_GET(self):
        self.handle_req(head=False)

    def handle_req(self, head=False):
        path = self.path.split("?")[0]
        # 1. _redirects 优先（Pages 就是这么排的）
        if path in RULES:
            dst, code = RULES[path]
            self.send_response(int(code))
            self.send_header("Location", dst)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        # 2. 静态文件
        rel = path.lstrip("/")
        cand = [os.path.join(SITE, rel)]
        if rel.endswith("/") or rel == "":
            cand = [os.path.join(SITE, rel, "index.html")]
        body = None
        ctype = "text/html; charset=utf-8"
        for c in cand:
            if os.path.isfile(c):
                with open(c, "rb") as f:
                    body = f.read()
                ctype = mimetypes.guess_type(c)[0] or "application/octet-stream"
                if ctype.startswith("text/") or ctype in (
                        "application/xml", "image/svg+xml"):
                    ctype += "; charset=utf-8"
                break
        if body is not None:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head:
                self.wfile.write(body)
            return

        # 3. 404.html 当响应体，状态码 404
        p404 = os.path.join(SITE, "404.html")
        body = b"404 not found"
        if os.path.exists(p404):
            with open(p404, "rb") as f:
                body = f.read()
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head:
            self.wfile.write(body)


if __name__ == "__main__":
    print("preview on http://127.0.0.1:{}  (site={}, rules={})".format(
        PORT, SITE, len(RULES)))
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
