#!/usr/bin/env python3
# ILANG
# TYPE script
# PROJECT vps-deals-promo-radar
# ROLE 从每个厂商官网抓 logo 存进 assets/logos/ 结果写 data/logos.json
#       抓不到的留空 build 回退成首字母 不许拿别的图顶替
# BOUNDARY never:绕过反爬 伪造 UA 抓登录后内容|scope:permanent
# BOUNDARY never:编优惠 编价格 编佣金|scope:permanent
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
ILANG_FILE = os.path.join(ROOT, ".ilang", "site.ilang")
LOGO_DIR = os.path.join(ROOT, "assets", "logos")
OUT_FILE = os.path.join(ROOT, "data", "logos.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

# 走直连，不吃环境代理
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
OPENER.addheaders = [("User-Agent", UA),
                     ("Accept", "text/html,application/xhtml+xml,*/*;q=0.8")]


def parse_ilang_providers(path):
    """复用 scraper 的解析器，保证厂商清单只有一个来源。"""
    sys.path.insert(0, ROOT)
    from scraper import parse_ilang
    return parse_ilang(path)["PROVIDERS"]


def fetch(url, timeout=20):
    try:
        with OPENER.open(url, timeout=timeout) as r:
            return r.getcode(), r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, None, ""
    except Exception:
        return 0, None, ""


def abs_url(href, base):
    return urllib.parse.urljoin(base, href.strip())


def reg_domain(url):
    """取注册域名（去 www、取最后两段），判断图片是否来自厂商自己的站。"""
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return ""
    host = re.sub(r"^www\.", "", host)
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


# 这些路径里的 "logo" 不是厂商自己的 logo：
# 域名后缀图（tld-logos）、第三方评测站图（reviews/usersearch）、
# 支付/卡组织图（mastercard/visa/paypal…）—— 页面里常带，抓来会张冠李戴
BAD_LOGO_PATH = re.compile(
    r"(tld-logos?|/tld/|reviews?/|usersearch|/partner/|badge|award|"
    r"trustpilot|sitejabber|hostadvice|"
    r"mastercard|maestro|visa|amex|american-express|paypal|stripe|"
    r"applepay|googlepay|google-pay|bitcoin|crypto|ethereum|"
    r"money-back|guarantee|ssl|secure|norton|mcafee|"
    # 合规/认证徽章：路径里常带 /logo/ 但那是徽章不是厂商标
    r"gdpr|iso[-_ ]?\d|pci[-_]?dss|hipaa|soc[-_]?2|dmca|"
    r"certified|certificate|certification|compliance|"
    r"flag|/flags/|country|language|social|facebook|twitter|x-logo|"
    r"linkedin|youtube|instagram|tiktok|reddit|discord|telegram)", re.I)


def candidates_from_html(html, base):
    """按优先级收集 logo 候选。
    圆形头像要方图，所以 apple-touch-icon / 1:1 icon 排最前。
    页面里的 <img> 只收同源的、且路径不像域名后缀图或第三方评测图 ——
    否则会抓到 '.com 后缀图'、'别的站评测 logo' 这类张冠李戴的东西。
    """
    out = []
    site_dom = reg_domain(base)
    # 品牌词（域名主标签）—— 页面 <img> 类候选必须带它才算厂商自己的 logo，
    # 否则会把客户 testimonial 图、GDPR 徽章、支付图标当成厂标
    brand = re.sub(r"[^a-z0-9]", "", (site_dom.split(".")[0] or "").lower())

    def href_of(tag):
        # 压缩过的 HTML 里属性值常常不带引号（<link href=/favicon.png rel=icon>），
        # 只认带引号会把这类站点的图标全漏掉
        m = re.search(r'href=["\']?([^"\'\s>]+)', tag, re.I)
        return m.group(1) if m else None

    # 1. apple-touch-icon —— 通常 180x180 方图，做圆形头像最合适
    for m in re.finditer(r"<link[^>]*rel=[^>]*(?:apple-touch-icon)[^>]*>", html, re.I):
        h = href_of(m.group(0))
        if h:
            out.append(("apple", abs_url(h, base), 180, 1))

    # 2. <link rel="icon"> —— 方形优先，其次取最大的
    for m in re.finditer(r"<link[^>]*rel=[^>]*(?:shortcut\s+)?icon[^>]*>", html, re.I):
        tag = m.group(0)
        h = href_of(tag)
        if not h:
            continue
        sm = re.search(r'sizes=["\']?(\d+)x(\d+)', tag, re.I)
        if sm:
            w, hh = int(sm.group(1)), int(sm.group(2))
            out.append(("icon", abs_url(h, base), w, 1 if w == hh else 0))
        else:
            out.append(("icon", abs_url(h, base), 16, 0))

    # 3. 页面里带 logo 字样的 <img> —— 必须同源且路径干净
    for m in re.finditer(r"<img[^>]*>", html, re.I):
        tag = m.group(0)
        if not re.search(r"logo", tag, re.I):
            continue
        s = re.search(r'src=["\']?([^"\'\s>]+)', tag, re.I)
        if not s:
            continue
        u = abs_url(s.group(1), base)
        if not u.lower().endswith((".svg", ".png", ".webp", ".jpg", ".jpeg")):
            continue
        if BAD_LOGO_PATH.search(u):
            continue
        if reg_domain(u) != site_dom:
            continue
        # 只看路径+查询串（不看 host，因为同域的图 host 当然带品牌词）
        tail = (urllib.parse.urlparse(u).path or "") + "?" + (urllib.parse.urlparse(u).query or "")
        if brand and brand not in tail.lower():
            continue
        out.append(("imglogo", u, 100, 0))

    # 排序：apple > 方形 icon(大的优先) > 非方形 icon(大的优先) > 同源 imglogo
    def key(x):
        order = {"apple": 0, "icon": 1, "imglogo": 2}
        return (order.get(x[0], 9), -x[3], -x[2])

    out.sort(key=key)
    return out


def ext_for(url, ctype):
    low = url.lower().split("?")[0]
    for e in (".svg", ".png", ".webp", ".jpg", ".jpeg", ".ico", ".gif"):
        if low.endswith(e):
            return ".svg" if e == ".svg" else (".png" if e in (".png", ".webp", ".gif") else e)
    if "svg" in ctype:
        return ".svg"
    if "png" in ctype:
        return ".png"
    if "jpeg" in ctype or "jpg" in ctype:
        return ".jpg"
    if "webp" in ctype:
        return ".png"
    if "icon" in ctype:
        return ".ico"
    return None


def main():
    providers = parse_ilang_providers(ILANG_FILE)
    os.makedirs(LOGO_DIR, exist_ok=True)
    results = {}

    for p in providers:
        slug = re.sub(r"[^a-z0-9]+", "-", p["name"].lower()).strip("-")
        site = p["url"] or p["source_url"]
        print("  {:<20s} {}".format(p["name"], site))
        rec = {"name": p["name"], "slug": slug, "site": site,
               "logo_file": None, "source": None, "status": "missing"}

        code, body, _ = fetch(site)
        if code != 200 or not body:
            rec["status"] = "site_unreachable_http_%s" % code
            print("      site unreachable (HTTP {})".format(code))
            results[slug] = rec
            time.sleep(0.4)
            continue

        html = body.decode("utf-8", "replace")
        cands = candidates_from_html(html, site)
        cands.append(("favicon", abs_url("/favicon.ico", site), 0))

        got = False
        wide_fallback = None   # 横版 logo 留作最后手段
        for cand in cands:
            kind, url = cand[0], cand[1]
            c2, data, ctype = fetch(url)
            if c2 != 200 or not data:
                continue
            if not ctype.lower().startswith("image"):
                continue
            if len(data) < 300 or len(data) > 3_000_000:
                continue
            ext = ext_for(url, ctype)
            if not ext:
                continue

            # 圆形头像要方图：比例极端的（横幅/长条）先不收，留作备选
            if ext != ".svg":
                try:
                    from PIL import Image
                    im = Image.open(io.BytesIO(data))
                    rt = im.size[0] / max(1, im.size[1])
                    if rt > 3.0 or rt < 0.34:
                        if wide_fallback is None:
                            wide_fallback = (kind, url, data, ext)
                        continue
                except Exception:
                    pass

            fname = slug + ext
            with open(os.path.join(LOGO_DIR, fname), "wb") as f:
                f.write(data)
            rec.update({"logo_file": fname, "source": url,
                        "status": "ok", "bytes": len(data), "kind": kind})
            print("      ok {:<6s} {:>8d}B  {}".format(kind, len(data), url[:62]))
            got = True
            break

        if not got and wide_fallback:
            kind, url, data, ext = wide_fallback
            fname = slug + ext
            with open(os.path.join(LOGO_DIR, fname), "wb") as f:
                f.write(data)
            rec.update({"logo_file": fname, "source": url, "status": "ok_wide",
                        "bytes": len(data), "kind": kind})
            print("      ok {:<6s} {:>8d}B  {} (横版,需 contain)".format(
                kind, len(data), url[:52]))
            got = True

        if not got:
            rec["status"] = "no_image_found"
            print("      no usable logo -> 回退首字母")

        results[slug] = rec
        time.sleep(0.4)

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "logos": results}, f, ensure_ascii=False, indent=2)

    ok = sum(1 for r in results.values() if r["status"] == "ok")
    print("\nwrote", OUT_FILE)
    print("providers={} logos_ok={} fallback={}".format(
        len(results), ok, len(results) - ok))


if __name__ == "__main__":
    main()
