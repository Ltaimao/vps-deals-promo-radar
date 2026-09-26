#!/usr/bin/env python3
# ILANG
# TYPE script
# PROJECT vps-deals-promo-radar
# ROLE 对 0 offers 的厂商，用真浏览器(CDP)打开官方页，取渲染后的 DOM 再抽一次价
#       取到就写 data/refetch.json 交给 build 并进那一页
#       取不到就标 empty，build 会把该页下线 + 从 sitemap 撤 + 老地址 301 回上位页
# BOUNDARY never:编价格 编优惠 拿标准文字顶替抓不到的价格|scope:permanent
# BOUNDARY never:绕过反爬 伪造 UA 抓登录后内容|scope:permanent
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from scraper import parse_ilang, extract_offers, strip_tags, PRICE_RE  # noqa: E402

ILANG_FILE = os.path.join(ROOT, ".ilang", "site.ilang")
OFFERS = os.path.join(ROOT, "data", "offers.json")
OUT = os.path.join(ROOT, "data", "refetch.json")
CDP = "http://127.0.0.1:9222"

try:
    import websocket
except ImportError:
    print("need websocket-client", file=sys.stderr)
    sys.exit(2)


def page_ws():
    d = json.loads(urllib.request.urlopen(CDP + "/json", timeout=5).read())
    for t in d:
        if t.get("type") == "page":
            return t.get("webSocketDebuggerUrl")
    return None


class Tab:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=40)
        self.mid = 0

    def call(self, method, params=None, timeout=40):
        self.mid += 1
        msg = {"id": self.mid, "method": method}
        if params:
            msg["params"] = params
        self.ws.send(json.dumps(msg))
        self.ws.settimeout(timeout)
        while True:
            d = json.loads(self.ws.recv())
            if d.get("id") == self.mid:
                if "error" in d:
                    raise RuntimeError(d["error"])
                return d.get("result")

    def eval(self, js, timeout=40):
        r = self.call("Runtime.evaluate",
                      {"expression": js, "returnByValue": True,
                       "awaitPromise": False}, timeout=timeout)
        return r.get("result", {}).get("value")

    def load(self, url, settle=6.0):
        """导航 + 等渲染。返回真实主文档 HTTP 状态码（来自 Navigation Timing）。"""
        self.call("Page.enable")
        self.call("Page.navigate", {"url": url})
        deadline = time.time() + 40
        while time.time() < deadline:
            try:
                if self.eval("document.readyState") == "complete":
                    break
            except Exception:
                pass
            time.sleep(0.5)
        time.sleep(2)
        # 触发懒加载：滚到底再回顶
        try:
            self.eval("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.5)
            self.eval("window.scrollTo(0, 0)")
        except Exception:
            pass
        time.sleep(settle)
        try:
            st = self.eval(
                "(performance.getEntriesByType('navigation')[0]||{}).responseStatus")
        except Exception:
            st = None
        return st

    def html(self):
        return self.eval("document.documentElement.outerHTML") or ""

    def title(self):
        return self.eval("document.title") or ""


def evidence(text, price_val, currency):
    """把价格在页面文本里的上下文留一份 —— 报告里的每个价都要能指出出处。"""
    sym = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "CNY": "¥"}.get(currency, "$")
    # 页面上写 "$4 per month" 而不是 "$4.00"，两种写法都得认
    i = -1
    for needle in ("{}{:.2f}".format(sym, price_val),
                   "{}{}".format(sym, int(price_val) if price_val == int(price_val) else price_val),
                   "{}{}".format(sym, price_val)):
        i = text.find(needle)
        if i >= 0:
            break
    if i < 0:
        return ""
    s = max(0, i - 120)
    return re.sub(r"\s+", " ", text[s:i + 120]).strip()


def main():
    cfg = parse_ilang(ILANG_FILE)
    with open(OFFERS, "r", encoding="utf-8") as f:
        data = json.load(f)

    have = {d.get("provider_slug") for d in data["deals"]}
    targets = [p for p in data["providers"] if p["slug"] not in have]
    print("0 offers 的厂商:", [p["slug"] for p in targets])

    ws = page_ws()
    if not ws:
        print("CDP 没起来 —— 先跑 chrome_cdp_watchdog.py", file=sys.stderr)
        sys.exit(3)
    tab = Tab(ws)

    results = {}
    for p in targets:
        slug, name = p["slug"], p["name"]
        url = p["source_url"] or p["url"]
        print("  {:<18s} {}".format(slug, url))
        rec = {"name": name, "slug": slug, "url": url, "status": "empty",
               "http_status": None, "page_title": None, "rendered_bytes": 0,
               "deals": []}
        try:
            st = tab.load(url)
            html = tab.html()
            rec["http_status"] = st
            rec["page_title"] = tab.title()
            rec["rendered_bytes"] = len(html)
            text = strip_tags(html)
            deals = extract_offers(html, url, name)
            for d in deals:
                d["provider_slug"] = slug
                d["provider_name"] = name
                d["fetched_at"] = datetime.now(timezone.utc).isoformat()
                d["evidence"] = evidence(text, d["price"], d["currency"])
                d["via"] = "cdp_render"
            rec["deals"] = deals
            rec["status"] = "ok" if deals else "empty"
            print("      http={} rendered={}B title={!r} deals={}".format(
                st, len(html), (rec["page_title"] or "")[:50], len(deals)))
            for d in deals[:3]:
                print("        {} {} | {}".format(
                    d["currency"], d["price"], d["evidence"][:80]))
        except Exception as ex:
            rec["status"] = "error"
            rec["error"] = str(ex)[:200]
            print("      ERROR", str(ex)[:160])
        results[slug] = rec
        time.sleep(1)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
                   "results": results}, f, ensure_ascii=False, indent=2)

    ok = [s for s, r in results.items() if r["status"] == "ok"]
    empty = [s for s, r in results.items() if r["status"] != "ok"]
    print("\nwrote", OUT)
    print("refetch ok={} empty={}".format(len(ok), len(empty)))
    print("  ok   :", ok)
    print("  empty:", empty)


if __name__ == "__main__":
    main()
