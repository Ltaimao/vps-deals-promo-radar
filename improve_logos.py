#!/usr/bin/env python3
# ILANG
# TYPE script
# PROJECT vps-deals-promo-radar
# ROLE logo 择优补抓：对每个厂商的所有候选图标都下载量一遍尺寸
#       按「方图优先 + 越大越好 + 矢量优先」打分挑最好的一张
#       只替换比现有更好的，抓不到的保持原样（首字母兜底）
# BOUNDARY never:绕过反爬 伪造 UA 抓登录后内容|scope:permanent
# BOUNDARY never:拿别站的图冒充厂商 logo|scope:permanent
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from fetch_logos import (LOGO_DIR, OUT_FILE, OPENER, fetch, abs_url,
                         reg_domain, candidates_from_html, ext_for,
                         parse_ilang_providers, BAD_LOGO_PATH)

# 站点常放但首页 HTML 里不一定 link 出来的标准路径
COMMON_PATHS = [
    "/apple-touch-icon.png",
    "/apple-touch-icon-precomposed.png",
    "/favicon-192x192.png",
    "/android-chrome-192x192.png",
    "/favicon-96x96.png",
]
PROBE_HOSTS = ("{scheme}://{host}", "{scheme}://www.{host}")

# 换后缀后残留的旧文件，最后统一打出来由人决定是否删
ORPHANS = []


def svg_ratio(data):
    """从 svg 的 viewBox / width / height 取宽高比，取不到就当方图。"""
    try:
        head = data[:4096].decode("utf-8", "replace")
    except Exception:
        return 1.0
    m = re.search(r'viewBox=["\']([^"\']+)["\']', head)
    if m:
        nums = re.findall(r"-?\d+(?:\.\d+)?", m.group(1))
        if len(nums) >= 4:
            w, h = float(nums[2]), float(nums[3])
            return w / h if h else 1.0
    m = re.search(r'width=["\']([\d.]+)(?:px)?["\']', head)
    m2 = re.search(r'height=["\']([\d.]+)(?:px)?["\']', head)
    if m and m2:
        w, h = float(m.group(1)), float(m2.group(1))
        return w / h if h else 1.0
    return 1.0


def measure(data, ext):
    """返回 (w, h, ratio)。svg 用 viewBox 估，量不出来返回 (0,0,1)。"""
    if ext == ".svg":
        r = svg_ratio(data)
        return (0, 0, r)
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        w, h = im.size
        return (w, h, w / h if h else 1.0)
    except Exception:
        return (0, 0, 1.0)


def score(data, ext):
    """越大越好。方图优先、尺寸越大越好、矢量（可无限缩放）优先。"""
    w, h, r = measure(data, ext)
    if ext == ".svg":
        # 矢量：只要不是极端长条就给高分
        if 0.34 <= r <= 3.0:
            base = 8000
            if 0.8 <= r <= 1.25:
                base += 2000
            return base
        return 300
    s = min(w, h)
    if s <= 0:
        return 0
    if 0.8 <= r <= 1.25:
        sq = 1.0
    elif 0.5 <= r <= 2.0:
        sq = 0.6
    else:
        sq = 0.12
    val = sq * min(s, 256) * 10
    if ext == ".ico":
        val *= 0.8
    return val


def existing_score(fname):
    if not fname:
        return -1
    p = os.path.join(LOGO_DIR, fname)
    if not os.path.exists(p):
        return -1
    with open(p, "rb") as f:
        data = f.read()
    return score(data, os.path.splitext(fname)[1].lower())


def collect(site, html):
    """收集全部候选 URL（去重）。"""
    seen, urls = set(), []
    for cand in candidates_from_html(html, site):
        if cand[1] not in seen:
            seen.add(cand[1])
            urls.append((cand[0], cand[1]))
    # 不收 og:image —— 首页 og:image 通常是 1200x630 的营销大图/截图，
    # 不是厂商 logo，拿它当头像会张冠李戴（::BOUNDARY 不许拿别图冒充）。
    # 标准路径探测（同源）
    parts = urllib.parse.urlparse(site)
    host = re.sub(r"^www\.", "", parts.hostname or "")
    for tmpl in PROBE_HOSTS:
        root = tmpl.format(scheme=parts.scheme or "https", host=host)
        for pth in COMMON_PATHS:
            u = root + pth
            if u not in seen:
                seen.add(u)
                urls.append(("common", u))
    return urls


def pick(site, html):
    """下载所有候选取分最高的一个。返回 dict 或 None。"""
    best = None
    for kind, url in collect(site, html):
        c2, data, ctype = fetch(url, timeout=15)
        if c2 != 200 or not data:
            continue
        if not ctype.lower().startswith("image"):
            continue
        if len(data) < 300 or len(data) > 3_000_000:
            continue
        ext = ext_for(url, ctype)
        if not ext:
            continue
        # 只收厂商自己域名下的图
        if reg_domain(url) != reg_domain(site):
            continue
        sc = score(data, ext)
        if best is None or sc > best["score"]:
            best = {"kind": kind, "url": url, "data": data, "ext": ext,
                    "score": sc, "bytes": len(data)}
    return best


def main():
    only = None
    if len(sys.argv) > 1 and sys.argv[1].startswith("--only="):
        only = set(sys.argv[1].split("=", 1)[1].split(","))
    providers = parse_ilang_providers(os.path.join(ROOT, ".ilang", "site.ilang"))
    with open(OUT_FILE, "r", encoding="utf-8") as f:
        doc = json.load(f)
    logos = doc["logos"]

    for p in providers:
        slug = re.sub(r"[^a-z0-9]+", "-", p["name"].lower()).strip("-")
        if only and slug not in only:
            continue
        site = p["url"] or p["source_url"]
        rec = logos.get(slug, {"name": p["name"], "slug": slug, "site": site,
                               "logo_file": None, "source": None, "status": "missing"})
        cur = existing_score(rec.get("logo_file"))
        print("  {:<20s} cur={}".format(slug, round(cur)))

        code, body, _ = fetch(site)
        if code != 200 or not body:
            print("      site unreachable (HTTP {}) — keep".format(code))
            time.sleep(0.3)
            continue
        html = body.decode("utf-8", "replace")
        best = pick(site, html)
        if not best:
            print("      no candidate — keep")
            time.sleep(0.3)
            continue
        if best["score"] <= cur:
            print("      keep existing ({} >= {})".format(round(cur), round(best["score"])))
            time.sleep(0.3)
            continue
        fname = slug + best["ext"]
        with open(os.path.join(LOGO_DIR, fname), "wb") as f:
            f.write(best["data"])
        # 换了后缀旧文件会变孤儿，这里只记录、不自动删（删文件要人确认）
        old = rec.get("logo_file")
        if old and old != fname:
            ORPHANS.append(old)
        rec.update({"name": p["name"], "slug": slug, "site": site,
                    "logo_file": fname, "source": best["url"],
                    "status": "ok", "bytes": best["bytes"], "kind": best["kind"]})
        logos[slug] = rec
        print("      -> {} ({}) score={} {}".format(
            fname, best["kind"], round(best["score"]), best["url"][:60]))
        time.sleep(0.3)

    doc["logos"] = logos
    doc["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print("\nwrote", OUT_FILE)
    if ORPHANS:
        print("orphan files (旧后缀残留，需人工确认后删):", ", ".join(sorted(set(ORPHANS))))


if __name__ == "__main__":
    main()
