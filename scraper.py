#!/usr/bin/env python3
# ILANG
# TYPE script
# PROJECT vps-deals-promo-radar
# ROLE 从 .ilang/site.ilang 读厂商清单 抓每个公开页面 提取真实可验证的优惠
#       写到 data/offers.json 任何抓不到的字段都留空或跳过 不许拿估的填
# BOUNDARY never:编优惠 编价格 编佣金 编汇率 编折扣|scope:permanent
# BOUNDARY never:绕过反爬 伪造 UA 抓登录后内容 违反 robots.txt|scope:permanent
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import urllib.parse
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
        "ANALYTICS": {}, "AFFILIATE": [],
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
            elif in_module == "ANALYTICS" and ":" in s:
                k, _, v = s.partition(":")
                cfg["ANALYTICS"][k.strip()] = v.strip()
            elif in_module == "AFFILIATE" and "|" in s:
                parts = [p.strip() for p in s.split("|")]
                if len(parts) < 4:
                    continue
                cfg["AFFILIATE"].append({
                    "name": parts[0],
                    "url": parts[1],
                    "blurb": parts[2],
                    "network": parts[3],
                    "logo": parts[4] if len(parts) > 4 and parts[4] else None,
                })
    return cfg


# ---------- fetch: robots policy applies to every destination ----------
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_http(url, timeout):
    """Return one HTTP response; redirects are handled explicitly by the caller."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,text/plain;q=0.9,*/*;q=0.8"})
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=timeout) as response:
            return response.status, response.read(), response.headers
    except urllib.error.HTTPError as error:
        return error.code, None, error.headers
    except (OSError, ValueError, urllib.error.URLError):
        return 0, None, {}


def valid_public_url(url):
    parts = urllib.parse.urlsplit(url)
    return parts.scheme in ("http", "https") and bool(parts.hostname) and not parts.username and not parts.password


class RobotsRules:
    """Select the most specific agent group and longest matching path (RFC 9309).

    urllib.robotparser is not used for authorization because it uses first-match
    paths and does not implement wildcard/end-anchor rules.
    """
    def __init__(self, text):
        groups, group = [], None
        directives = False
        for line in text.splitlines():
            line = line.split('#', 1)[0].strip()
            if not line or ':' not in line:
                continue
            field, value = (part.strip() for part in line.split(':', 1))
            field = field.lower()
            if field == 'user-agent':
                if group is None or directives:
                    group = {'agents': [], 'rules': [], 'delay': 0}
                    groups.append(group)
                    directives = False
                group['agents'].append(value.lower())
            elif group is not None:
                directives = True
                if field in ('allow', 'disallow') and value:
                    group['rules'].append((value, field == 'allow'))
                elif field == 'crawl-delay':
                    try:
                        group['delay'] = max(group['delay'], float(value))
                    except ValueError:
                        pass
                elif field == 'request-rate':
                    match = re.fullmatch(r'(\d+)\s*/\s*(\d+)', value)
                    if match and int(match[1]):
                        group['delay'] = max(group['delay'], int(match[2]) / int(match[1]))
        product = UA.split('/', 1)[0].lower()
        selected, specificity = [], -1
        for group in groups:
            score = max((0 if agent == '*' else len(agent)
                         for agent in group['agents'] if agent == '*' or (agent and agent in product)), default=-1)
            if score > specificity:
                selected, specificity = [group], score
            elif score == specificity and score >= 0:
                selected.append(group)
        self.rules = [rule for group in selected for rule in group['rules']]
        self.delay = max((group['delay'] for group in selected), default=0)

    @staticmethod
    def normalized(path):
        # Decode only unreserved ASCII octets; encoded slashes remain encoded.
        def octet(match):
            char = chr(int(match[0][1:], 16))
            return char if char.isascii() and (char.isalnum() or char in '-._~') else match[0].upper()
        return re.sub(r'%[0-9a-fA-F]{2}', octet,
                      urllib.parse.quote(path, safe="/%?=&;:+,@!$'()*-._~"))

    def allows(self, url):
        parts = urllib.parse.urlsplit(url)
        path = self.normalized(parts.path or '/')
        if parts.query:
            path += '?' + self.normalized(parts.query)
        matches = []
        for pattern, allow in self.rules:
            pattern = self.normalized(pattern)
            end = pattern.endswith('$')
            if end:
                pattern = pattern[:-1]
            regex = '^' + re.escape(pattern).replace(r'\*', '.*') + ('$' if end else '')
            if re.search(regex, path):
                matches.append((len(pattern.replace('*', '').encode('utf-8')), allow))
        return max(matches)[1] if matches else True


class RobotsClient:
    """Fail closed on unavailable rules; never fetch a disallowed redirect target.

    A missing robots file (404/410) permits access. 401/403, 429, server errors,
    invalid URLs and network errors do not. Rules are cached only for this run.
    """
    def __init__(self):
        self.rules = {}
        self.last_request = {}
        self.last_reason = None

    def policy(self, url, timeout=10):
        if not valid_public_url(url):
            return False, "invalid_url", 0
        parts = urllib.parse.urlsplit(url)
        origin = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        if origin not in self.rules:
            robots_url = origin + "/robots.txt"
            parser, failure = None, "robots_unavailable"
            for _ in range(6):
                code, body, headers = read_http(robots_url, timeout)
                if code in (301, 302, 303, 307, 308):
                    target = urllib.parse.urljoin(robots_url, headers.get("Location", ""))
                    if not headers.get("Location") or not valid_public_url(target):
                        break
                    robots_url = target
                    continue
                if code in (404, 410):
                    parser = RobotsRules("")
                elif code == 200 and body is not None:
                    text = body.decode("utf-8-sig", "replace")
                    # A challenge/login HTML response is not a usable robots policy.
                    if "<html" not in text.lower() and "<!doctype html" not in text.lower():
                        significant = [line.split("#", 1)[0].strip() for line in text.splitlines()]
                        if not any(significant) or re.search(r"(?im)^\s*(user-agent|sitemap)\s*:", text):
                            parser = RobotsRules(text)
                elif code in (401, 403):
                    failure = "robots_denied"
                break
            self.rules[origin] = parser, failure
        parser, failure = self.rules[origin]
        if parser is None:
            return False, failure, 0
        if not parser.allows(url):
            return False, "robots_disallowed", 0
        return True, None, parser.delay

    def fetch(self, url, timeout=20):
        self.last_reason = None
        for _ in range(6):
            allowed, reason, delay = self.policy(url, min(timeout, 10))
            if not allowed:
                self.last_reason = reason
                return 0, None
            parts = urllib.parse.urlsplit(url)
            origin = (parts.scheme, parts.netloc)
            wait = delay - (time.monotonic() - self.last_request.get(origin, float("-inf")))
            if wait > timeout:
                self.last_reason = "crawl_delay_exceeds_budget"
                return 0, None
            if wait > 0:
                time.sleep(wait)
            self.last_request[origin] = time.monotonic()
            code, body, headers = read_http(url, timeout)
            if code in (301, 302, 303, 307, 308):
                location = headers.get("Location")
                if not location:
                    self.last_reason = "invalid_redirect"
                    return code, None
                url = urllib.parse.urljoin(url, location)
                continue
            if code != 200 or not body:
                self.last_reason = "http_" + str(code) if code else "network_error"
                return code, None
            return code, body
        self.last_reason = "redirect_limit"
        return 0, None


_CLIENT = RobotsClient()


def fetch(url, timeout=20):
    return _CLIENT.fetch(url, timeout)


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
# 每个厂商最多收这么多条。到顶就停 —— 所以条数等于这个值时，
# 它是「至少这么多」，不是精确值。build 会把它显示成 "12+"，
# 不许拿被截断的数当精确数报出去。
MAX_DEALS_PER_PROVIDER = 12


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
        # Require a billing period immediately attached to this amount. Nearby
        # promotional text or an unrelated monthly price is not enough evidence.
        suffix = text[m.end():m.end() + 55]
        period_match = re.match(
            r"\s*(?:USD|EUR|GBP|JPY|CNY|CAD|AUD)?\s*(?:/\s*|per\s+)(months?|mo\b|years?|yr\b|annual\b|hours?|hr\b|days?|day\b)",
            suffix, re.I)
        if not period_match:
            continue
        unit = period_match.group(1).lower()
        billing_period = ("month" if unit.startswith("mo") else
                          "year" if unit.startswith(("y", "annual")) else
                          "hour" if unit.startswith("h") else "day")
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
            "billing_period": billing_period,
            "price_evidence": m.group(0) + period_match.group(0),
            "offer_url": source_url,
            "source_url": source_url,
            "valid_until": None,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
        if len(deals) >= MAX_DEALS_PER_PROVIDER:
            break
    return deals


# ---------- 稳定身份 ----------
# ::RULE{deal 身份键=provider_slug+offer_url+title 归一化小写去空白后哈希 价格不许进键}
# offer_id 在抓取时一次算好、永久稳定；build.py 的历史重建用完全相同的归一化
# 对无 offer_id 的旧快照补算（见 build.py::deal_history_key）。
def offer_id_for(provider_slug, offer_url, title):
    parts = [
        re.sub(r"\s+", " ", (p or "").strip().lower())
        for p in (provider_slug, offer_url, title)
    ]
    return hashlib.sha1("\x00".join(parts).encode("utf-8")).hexdigest()[:16]


# ---------- main ----------
def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main(output_file=None):
    output_file = output_file or OUT_FILE
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
            "fetch_reason": _CLIENT.last_reason,
            "fetched_at": now,
            "deals_capped": False,
        }
        if code == 200 and body:
            try:
                extracted = extract_offers(body.decode("utf-8", "replace"), url, name)
            except Exception as e:
                print("    parse error:", e, file=sys.stderr)
                extracted = []
            # 到顶说明后面还有没抓的 —— 把这件事记下来，别让下游把它当精确条数
            entry["deals_capped"] = len(extracted) >= MAX_DEALS_PER_PROVIDER
            for d in extracted:
                d["provider_slug"] = slug
                d["offer_id"] = offer_id_for(slug, d.get("offer_url"), d.get("title"))
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
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    ok = sum(1 for x in providers_out if x["fetch_status"] == "ok")
    print(f"\nwrote {output_file}")
    print(f"providers={len(providers_out)} ok={ok} unreachable={len(providers_out)-ok}")
    print(f"deals={len(deals_out)}")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch public provider pages with robots.txt checks.")
    parser.add_argument("--output", default=OUT_FILE, help="Output path (use a temporary path for validation).")
    sys.exit(main(parser.parse_args().output))