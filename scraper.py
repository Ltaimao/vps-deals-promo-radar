#!/usr/bin/env python3
# ILANG
# TYPE script
# PROJECT vps-deals-promo-radar
# ROLE 从 .ilang/site.ilang 读厂商清单 抓每个公开页面 提取真实可验证的优惠
#       写到 data/offers.json 任何抓不到的字段都留空或跳过 不许拿估的填
# BOUNDARY never:编优惠 编价格 编佣金 编汇率 编折扣|scope:permanent
# BOUNDARY never:绕过反爬 伪造 UA 抓登录后内容 违反 robots.txt|scope:permanent
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
ILANG_FILE = os.path.join(ROOT, ".ilang", "site.ilang")
OUT_FILE = os.path.join(ROOT, "data", "offers.json")
UA = "vps-deals-bot/1.0 (+https://github.com/vps-deals-promo-radar; contact via repo issues)"


# ---------- .ilang parser ----------
def parse_ilang(path):
    cfg = {
        "SITE": {}, "PROVIDERS": [], "FIELDS": [],
        "LOCALE": {}, "RENDER": {}, "SCHEDULE": {},
        "RULES": [], "BOUNDARIES": [],
    }
    in_module = None
    if not os.path.exists(path):
        print("missing", path, file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            s = line.strip()
            if not s or s.startswith("#"):
                continue

            m = re.match(r"::STATE\{@(\w+),\s*(.+?)\}\s*$", s)
            if m:
                attrs = dict(re.findall(r"(\w+):([^,]+?)(?=,|$)", m.group(2)))
                cfg["SITE"].update(attrs)
                continue

            m = re.match(r"::MODULE\{(\w+)(?:\|title:([^}]+))?\}\s*$", s)
            if m:
                in_module = m.group(1)
                continue

            m = re.match(r"::RULE\{(.+)\}\s*$", s)
            if m:
                cfg["RULES"].append(m.group(1).strip())
                in_module = None
                continue

            m = re.match(r"::BOUNDARY\{(.+)\}\s*$", s)
            if m:
                cfg["BOUNDARIES"].append(m.group(1).strip())
                in_module = None
                continue

            if s.startswith("::"):
                in_module = None
                continue

            if in_module == "PROVIDERS" and "|" in s:
                parts = [p.strip() for p in s.split("|")]
                if len(parts) < 4:
                    continue
                affiliate = parts[3] if parts[3] and not parts[3].startswith("http") else None
                cfg["PROVIDERS"].append({
                    "name": parts[0],
                    "url": parts[1],
                    "source_url": parts[2],
                    "affiliate_url": affiliate,
                })
            elif in_module == "FIELDS":
                for w in re.findall(r"[a-z_]+", s):
                    cfg["FIELDS"].append(w)
            elif in_module == "LOCALE" and ":" in s:
                k, _, v = s.partition(":")
                cfg["LOCALE"][k.strip()] = v.strip()
            elif in_module == "RENDER" and ":" in s:
                k, _, v = s.partition(":")
                cfg["RENDER"][k.strip()] = v.strip()
            elif in_module == "SCHEDULE" and ":" in s:
                k, _, v = s.partition(":")
                cfg["SCHEDULE"][k.strip()] = v.strip()
    return cfg


# ---------- fetch ----------
def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.getcode(), r.read()
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return 0, None


# ---------- extraction ----------
PRICE_RE = re.compile(
    r"(?P<sym>[$€£¥])\s?(?P<n1>\d{1,4}(?:[.,]\d{2})?)"
    r"|(?P<n2>\d{1,4}(?:[.,]\d{2})?)\s?(?P<cur>USD|EUR|GBP|JPY|CNY|CAD|AUD)",
    re.I,
)
PERIOD_RE = re.compile(r"/\s?(?:mo(?:nth)?|yr|year|annual)|per\s+(?:month|year)|monthly|annually", re.I)
PCT_RE = re.compile(r"(\d{1,2})\s?%\s?(?:off|discount)", re.I)
SYMBOL_TO_CCY = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}
CHROME = re.compile(r"^(?:VIEW|LEARN|CLICK|SEE|BUY|GET|ORDER|FIND|EXPLORE|MORE|ALL|SHOW|READ|START|GET\s+STARTED)\b", re.I)


def strip_tags(html):
    t = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    t = re.sub(r"<style[\s\S]*?</style>", " ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = (t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
          .replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " "))
    return t


def extract_offers(html, source_url, provider_name):
    text = strip_tags(html)
    deals = []
    seen = set()
    for m in PRICE_RE.finditer(text):
        s = max(0, m.start() - 160)
        e = min(len(text), m.end() + 90)
        snippet = text[s:e]
        # Require a per-period hint (so we don't grab random dollar amounts in
        # disclaimers/footer) OR a deal keyword.
        if not (PERIOD_RE.search(snippet)
                or PCT_RE.search(snippet)
                or "promo" in snippet.lower()
                or "coupon" in snippet.lower()
                or "limited" in snippet.lower()
                or "deal" in snippet.lower()
                or "save " in snippet.lower()
                or "first year" in snippet.lower()):
            continue
        raw = m.group(0).strip()
        if raw in seen:
            continue
        seen.add(raw)
        price_str = m.group("n1") or m.group("n2")
        try:
            price_val = float(price_str.replace(",", "."))
        except Exception:
            continue
        if price_val <= 0 or price_val > 10000:
            continue
        currency = m.group("cur").upper() if m.group("cur") else SYMBOL_TO_CCY.get(m.group("sym"), "USD")
        # title: look back further for a heading or product name; skip UI chrome
        pre = text[max(0, m.start() - 200):m.start()].strip()
        # try headings like "### Plan Name" patterns first
        title = None
        for tm in re.finditer(r"([A-Z][\w\-/& ]{4,80})\s*$", pre, re.M):
            cand = tm.group(1).strip()
            if CHROME.match(cand):
                continue
            if cand.isupper() and len(cand) < 30:
                continue
            title = cand
            break
        if not title:
            # fall back to nearest reasonable noun phrase
            words = re.findall(r"\b[A-Z][a-zA-Z0-9\-/&]{2,}\b", pre)
            if words:
                title = " ".join(words[-3:])
        if not title:
            title = provider_name + " pricing"
        title = title.strip()
        if len(title) < 4 or len(title) > 200:
            continue
        deals.append({
            "title": title,
            "provider_name": provider_name,
            "price": price_val,
            "currency": currency,
            "offer_url": source_url,
            "source_url": source_url,
            "valid_until": None,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
        if len(deals) >= 12:
            break
    return deals


# ---------- main ----------
def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main():
    cfg = parse_ilang(ILANG_FILE)
    providers = cfg["PROVIDERS"]
    if not providers:
        print("::RULE 触发: .ilang/site.ilang 里没有 PROVIDERS 行", file=sys.stderr)
        sys.exit(1)

    providers_out, deals_out = [], []
    now = datetime.now(timezone.utc).isoformat()
    for p in providers:
        name = p["name"]
        slug = slugify(name)
        url = p["source_url"] or p["url"]
        print(f"  fetch {name:<28s} {url}")
        code, body = fetch(url)
        entry = {
            "name": name,
            "slug": slug,
            "url": p["url"],
            "source_url": url,
            "affiliate_url": p.get("affiliate_url"),
            "fetch_status": "ok" if (code == 200 and body) else "unreachable",
            "http_code": code,
            "fetched_at": now,
        }
        if code == 200 and body:
            try:
                extracted = extract_offers(body.decode("utf-8", "replace"), url, name)
            except Exception as e:
                print("    parse error:", e, file=sys.stderr)
                extracted = []
            for d in extracted:
                d["provider_slug"] = slug
                deals_out.append(d)
        providers_out.append(entry)
        time.sleep(0.6)

    out = {
        "generated_at": now,
        "source": "scraper.py + .ilang/site.ilang",
        "site": cfg["SITE"],
        "providers": providers_out,
        "deals": deals_out,
    }
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    ok = sum(1 for x in providers_out if x["fetch_status"] == "ok")
    print(f"\nwrote {OUT_FILE}")
    print(f"providers={len(providers_out)} ok={ok} unreachable={len(providers_out)-ok}")
    print(f"deals={len(deals_out)}")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())