#!/usr/bin/env python3
# ILANG
# TYPE script
# PROJECT vps-deals-promo-radar
# ROLE 把 scraper 的输出 + .ilang/site.ilang 渲染成静态站
#       同时生成 sitemap.xml robots.txt 和每页 JSON-LD
# BOUNDARY never:编优惠 编价格 编佣金 编汇率 编折扣|scope:permanent
import html
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def stable_suffix(seed: str) -> int:
    """Deterministic 0..99999 suffix. Python's built-in hash() is process-random
    (PYTHONHASHSEED), which would change deal slugs on every build and litter
    site/deals/ with orphan dirs. md5 -> int gives a stable id."""
    h = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return int(h, 16) % 100000

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "templates"
SITE = ROOT / "site"
DATA = ROOT / "data" / "offers.json"
ILANG_FILE = ROOT / ".ilang" / "site.ilang"

sys.path.insert(0, str(ROOT))
from scraper import parse_ilang, slugify  # reuse the parser


def e(s):
    return html.escape("" if s is None else str(s), quote=True)


def load_data():
    if not DATA.exists():
        return None
    with open(DATA, "r", encoding="utf-8") as f:
        return json.load(f)


def load_cfg():
    return parse_ilang(ILANG_FILE)


def load_template(name):
    return (TEMPLATES / name).read_text(encoding="utf-8")


def fill(template, mapping):
    out = template
    for k, v in mapping.items():
        out = out.replace(k, "" if v is None else str(v))
    return out


def nav_html(active):
    items = [("/", "Home"), ("/compare/", "Compare")]
    parts = []
    for href, label in items:
        body = ("<strong>" + e(label) + "</strong>") if active == href else e(label)
        parts.append('<a href="' + href + '">' + body + "</a>")
    return "\n".join(parts)


def crumbs_html(parts):
    # parts: list of (href_or_None, name)
    bits = []
    for i, (href, name) in enumerate(parts):
        if i > 0:
            bits.append(" / ")
        if href:
            bits.append('<a href="' + href + '">' + e(name) + "</a>")
        else:
            bits.append(e(name))
    return "".join(bits)


def hreflang_html(per_lang_urls, lang):
    # per_lang_urls: dict lang -> url; x-default points to lang
    tags = ['<link rel="alternate" hreflang="x-default" href="' + e(per_lang_urls.get(lang, "")) + '">']
    for lg, u in per_lang_urls.items():
        tags.append('<link rel="alternate" hreflang="' + e(lg) + '" href="' + e(u) + '">')
    return "\n".join(tags)


def jsonld_offer(deal, base_url):
    obj = {
        "@context": "https://schema.org",
        "@type": "Offer",
        # 不用抓坏的 title 原文，改用真实字段生成的名字
        "name": offer_label(deal, 1),
        "url": deal.get("offer_url") or deal.get("source_url"),
        "price": deal.get("price"),
        "priceCurrency": deal.get("currency"),
    }
    if deal.get("valid_until"):
        obj["priceValidUntil"] = deal["valid_until"]
    obj["seller"] = {"@type": "Organization", "name": deal.get("provider_name", "")}
    return json.dumps(obj, ensure_ascii=False, indent=2)


def jsonld_itemlist(items, base_url):
    obj = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "itemListElement": items,
    }
    return json.dumps(obj, ensure_ascii=False, indent=2)


def jsonld_service(provider, deals, base_url):
    offers = []
    for i, d in enumerate(deals):
        if not d.get("price"):
            continue
        offers.append({
            "@type": "Offer",
            "name": offer_label(d, i + 1),
            "url": d.get("offer_url") or d.get("source_url"),
            "price": d.get("price"),
            "priceCurrency": d.get("currency"),
        })
    obj = {
        "@context": "https://schema.org",
        "@type": "Service",
        "name": provider["name"],
        "url": provider["url"],
        "provider": {"@type": "Organization", "name": provider["name"]},
        "offers": offers,
    }
    return json.dumps(obj, ensure_ascii=False, indent=2)


def render_index(ctx, data, cfg, base_url):
    providers = data["providers"]
    deals = data["deals"]
    provider_links = "\n".join(
        '<li><a href="/providers/{slug}/">{name}</a></li>'.format(slug=p["slug"], name=e(p["name"]))
        for p in providers
    )
    deal_cards = []
    for d in deals:
        badge = ""
        if d.get("valid_until"):
            try:
                if datetime.fromisoformat(d["valid_until"].replace("Z", "+00:00")) < datetime.now(timezone.utc):
                    badge = ' <span class="badge expired">expired</span>'
            except Exception:
                pass
        if not d.get("price"):
            badge += ' <span class="badge">no price</span>'
        price_label = ("$" + "{:.2f}".format(d["price"]) + " " + d.get("currency", "")) if d.get("price") else "—"
        # ::RULE{出口只有一个} — 卡片指向所属厂商页的动态层，不再开 /deals/ 网址
        # ::RULE{抓坏的字段一律不许留} — 卡片标题由厂商名+价格生成
        prov_url = "/providers/" + e(d.get("provider_slug", "")) + "/"
        card = (
            '<div class="deal">'
            '<div class="head">'
            '<h3><a href="{purl}">{label}</a>{badge}</h3>'
            '<span class="price">{price}</span>'
            '</div>'
            '<div class="meta">Go to <a href="{purl}">{pname} deals</a></div>'
            '</div>'
        ).format(
            purl=prov_url,
            label=e(offer_label(d, len(deal_cards) + 1)),
            badge=badge,
            price=e(price_label),
            pname=e(d.get("provider_name", "")),
        )
        deal_cards.append(card)
    if not deal_cards:
        deal_cards = ['<div class="deal"><p>No structured deals extracted from the listed providers this run. The scraper only writes entries when it can verify title + price + currency + URL together. If a provider\'s page is unreachable, it\'s listed below as <em>unreachable</em>.</p></div>']

    # ItemList 指向厂商页（出口唯一），不再指向已下线的 /deals/ 网址
    deal_index = []
    seen_prov = set()
    for d in deals:
        pslug = d.get("provider_slug", "")
        if not pslug or pslug in seen_prov:
            continue
        seen_prov.add(pslug)
        deal_index.append({
            "@type": "ListItem",
            "position": len(deal_index) + 1,
            "url": base_url + "/providers/" + pslug + "/",
            "name": d.get("provider_name", ""),
        })

    content = fill(load_template("index.html"), {
        "{{CRUMBS}}": crumbs_html([("", cfg["SITE"].get("brand", "vps-deals"))]),
        "{{BRAND_DISPLAY}}": e(cfg["SITE"].get("brand", "vps-deals")),
        "{{PROVIDER_COUNT}}": str(len(providers)),
        "{{PROVIDER_LIST}}": provider_links,
        "{{DEAL_COUNT}}": str(len(deals)),
        "{{DEAL_CARDS}}": "\n".join(deal_cards),
    })

    jsonld = jsonld_itemlist(deal_index, base_url) if deal_index else ""

    return render_base(ctx, content, jsonld)


def render_provider(ctx, data, cfg, base_url, provider):
    slug = provider["slug"]
    deals = [d for d in data["deals"] if d.get("provider_slug") == slug]
    if deals:
        rows = ["<table><thead><tr><th>Offer</th><th>Price</th><th>Currency</th><th>Source</th></tr></thead><tbody>"]
        for i, d in enumerate(deals, 1):
            url = d.get("offer_url") or d.get("source_url") or "#"
            # ::RULE{抓坏的字段一律不许留} — 行标签由真实字段生成(厂商名+价格)，
            # 不显示 scraper 抓出来的半截原文（如 'Search Multiple Transfer'）。
            label = offer_label(d, i)
            price_label = money(d.get("price"), d.get("currency")) or "—"
            rows.append(
                "<tr><td><a href=\"{offer}\">{label}</a></td><td>{price}</td><td>{cur}</td><td><a href=\"{src}\">source</a></td></tr>".format(
                    offer=e(url), label=e(label), price=e(price_label),
                    cur=e(d.get("currency", "")), src=e(d.get("source_url", ""))
                )
            )
        rows.append("</tbody></table>")
        deal_table = "\n".join(rows)
    elif provider["fetch_status"] == "ok":
        deal_table = '<p>Page reachable but no structured deal extracted this run. We only write a deal when title + price + currency + URL can all be verified.</p>'
    else:
        deal_table = '<p><span class="badge unreachable">unreachable</span> HTTP {} — provider page did not return 200. Try again on the next run, or check the URL.</p>'.format(e(provider["http_code"]))

    content = fill(load_template("provider.html"), {
        "{{CRUMBS}}": crumbs_html([("/", "Home"), ("", e(provider["name"]))]),
        "{{PROVIDER_NAME}}": e(provider["name"]),
        "{{PROVIDER_URL}}": e(provider["url"]),
        "{{SOURCE_URL}}": e(provider["source_url"]),
        "{{DEAL_TABLE}}": deal_table,
        "{{LAST_FETCHED_AT}}": e(provider["fetched_at"][:19].replace("T", " ") + " UTC"),
    })

    jsonld = jsonld_service(provider, deals, base_url)

    return render_base(ctx, content, jsonld)


def render_deal(ctx, data, cfg, base_url, deal):
    deal_id = slugify(deal["title"])[:60] + "-" + str(stable_suffix(deal["title"] + "|" + deal.get("provider_slug", "")))
    valid_row = ""
    if deal.get("valid_until"):
        valid_row = "<dt>Valid until</dt><dd>" + e(deal["valid_until"]) + "</dd>"

    faq_block = ""

    content = fill(load_template("deal.html"), {
        "{{CRUMBS}}": crumbs_html([("/", "Home"),
                                   ("/providers/" + deal.get("provider_slug", "") + "/", e(deal.get("provider_name", ""))),
                                   ("", e(deal["title"]))]),
        "{{DEAL_TITLE}}": e(deal["title"]),
        "{{PRICE_LABEL}}": ("$" + "{:.2f}".format(deal["price"]) + " " + deal.get("currency", "")) if deal.get("price") else "—",
        "{{PROVIDER_NAME}}": e(deal.get("provider_name", "")),
        "{{PROVIDER_SLUG}}": e(deal.get("provider_slug", "")),
        "{{CURRENCY}}": e(deal.get("currency", "")),
        "{{DEAL_DESCRIPTION}}": "Live public pricing entry from " + e(deal.get("provider_name", "")) + ". Source: " + '<a href="' + e(deal.get("source_url", "")) + '">' + e(deal.get("source_url", "")) + "</a>.",
        "{{OFFER_URL}}": e(deal.get("offer_url") or deal.get("source_url", "")),
        "{{OFFER_URL_LABEL}}": e((deal.get("offer_url") or deal.get("source_url", ""))[:80]),
        "{{SOURCE_URL}}": e(deal.get("source_url", "")),
        "{{SOURCE_URL_LABEL}}": e((deal.get("source_url", ""))[:80]),
        "{{VALID_UNTIL_ROW}}": valid_row,
        "{{FETCHED_AT_LABEL}}": e(deal["fetched_at"][:19].replace("T", " ") + " UTC"),
        "{{BUILT_AT}}": e(datetime.now(timezone.utc).isoformat()[:19].replace("T", " ") + " UTC"),
        "{{FAQ_BLOCK}}": faq_block,
    })

    jsonld = jsonld_offer(deal, base_url)
    return render_base(ctx, content, jsonld)


def render_compare(ctx, data, cfg, base_url):
    rows = []
    for p in data["providers"]:
        deals_for_p = [d for d in data["deals"] if d.get("provider_slug") == p["slug"]]
        status = ('<span class="badge">reachable</span>' if p["fetch_status"] == "ok"
                  else '<span class="badge unreachable">unreachable</span>')
        rows.append(
            "<tr><td><a href=\"/providers/{slug}/\">{name}</a></td><td>{status}<br>HTTP {code}</td><td>{n}</td><td><a href=\"{src}\">source</a></td></tr>".format(
                slug=e(p["slug"]), name=e(p["name"]), status=status,
                code=e(p["http_code"]), n=str(len(deals_for_p)), src=e(p["source_url"])
            )
        )

    content = fill(load_template("compare.html"), {
        "{{CRUMBS}}": crumbs_html([("/", "Home"), ("", "Compare")]),
        "{{PROVIDER_COUNT}}": str(len(data["providers"])),
        "{{ROWS}}": "\n".join(rows),
    })

    itemlist = []
    for i, p in enumerate(data["providers"]):
        itemlist.append({
            "@type": "ListItem",
            "position": i + 1,
            "url": base_url + "/providers/" + p["slug"] + "/",
            "name": p["name"],
        })
    jsonld = jsonld_itemlist(itemlist, base_url)
    return render_base(ctx, content, jsonld)


def offer_label(deal, index):
    """单条优惠的显示名 —— 由真实字段生成(厂商名 + 价格)，不编、也不用抓坏的原文。
    抓到的 title 常是半截 UI 文本（'Search Multiple Transfer'、'Standard GiB-month High'），
    按 RULE 一律不许留，改用可溯源的真实字段组合。"""
    name = deal.get("provider_name") or "Provider"
    price = money(deal.get("price"), deal.get("currency"))
    if price:
        return "{} offer #{} — {}".format(name, index, price)
    return "{} offer #{}".format(name, index)


def money(value, currency):
    """把价格格式化成 $X.XX 样式。拿不到价格就返回 None，不许编。"""
    if value is None:
        return None
    sym = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "CAD": "C$",
           "AUD": "A$", "CNY": "¥"}.get(currency, "$")
    return "{}{:.2f}".format(sym, float(value))


def current_month_year():
    """数据里最近一次抓取的年月 —— 月份来自数据，不是来自 build 时的系统时钟。"""
    return None


def provider_page_copy(provider, deals):
    """::RULE{每页 title 和 description 由数据生成 带厂商名 优惠幅度 月份}
    抓来的字段原文（如 'Search Multiple Transfer'）一律不许当标题。
    title      = 厂商名 + 优惠幅度 + 月份
    description= 厂商名 + 条数 + 最低价 + 月份
    拿不到价格的厂商不写价格，只写条数 —— 不许拿估的填。
    """
    name = provider["name"]
    month = None
    for d in deals:
        if d.get("fetched_at"):
            try:
                month = datetime.fromisoformat(
                    d["fetched_at"].replace("Z", "+00:00")).strftime("%B %Y")
                break
            except Exception:
                continue
    if not month and provider.get("fetched_at"):
        try:
            month = datetime.fromisoformat(
                provider["fetched_at"].replace("Z", "+00:00")).strftime("%B %Y")
        except Exception:
            month = None

    prices = [d.get("price") for d in deals if d.get("price")]
    cur = next((d.get("currency") for d in deals if d.get("currency")), "USD")

    title = name + " VPS Deals"
    if prices:
        title += " — from " + money(min(prices), cur) + "/mo"
    if month:
        title += " (" + month + ")"

    desc = name + " VPS hosting deals and public pricing, updated"
    if month:
        desc += " " + month
    desc += "."
    if prices:
        desc += " " + str(len(prices)) + " live offers from " + money(min(prices), cur) + "/mo."
    else:
        desc += " " + str(len(deals)) + " live offers listed."
    desc += " Nothing here is invented — every figure comes from " + name + "'s own public page."

    return title, desc


def render_base(ctx, content_html, jsonld_text):
    base = load_template("_base.html")
    subs = {
        "{{TITLE}}": e(ctx["title"]),
        "{{META_DESCRIPTION}}": e(ctx["meta_description"]),
        "{{CANONICAL_URL}}": e(ctx["canonical_url"]),
        "{{HREFLANG_TAGS}}": ctx.get("hreflang_tags", ""),
        "{{OG_TITLE}}": e(ctx["og_title"]),
        "{{OG_DESC}}": e(ctx["og_description"]),
        "{{OG_TYPE}}": e(ctx.get("og_type", "website")),
        "{{BRAND_NAME}}": e(ctx["brand"]),
        "{{NAV}}": ctx["nav"],
        "{{CONTENT}}": content_html,
        "{{LANG}}": e(ctx["lang"]),
        "{{LAST_FETCHED_AT}}": e(ctx["last_fetched_at"]),
        "{{REPO_FULL}}": e(ctx["repo_full"]),
        "{{JSONLD}}": jsonld_text,
    }
    out = base
    for k, v in subs.items():
        out = out.replace(k, "" if v is None else str(v))
    return out


def write(path, html_text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_text)


def write_sitemap(paths, out_path, base_url):
    seen = set()
    urls = []
    for p in paths:
        loc = base_url + "/" + p["path"]
        if loc in seen:
            continue
        seen.add(loc)
        urls.append({"loc": loc, "lastmod": p["lastmod"]})
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    )
    for u in urls:
        body += "  <url><loc>" + e(u["loc"]) + "</loc>"
        if u["lastmod"]:
            body += "<lastmod>" + e(u["lastmod"])[:10] + "</lastmod>"
        body += "</url>\n"
    body += "</urlset>\n"
    write(out_path, body)


def write_robots(out_path, base_url):
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Sitemap: " + base_url + "/sitemap.xml\n"
    )
    write(out_path, body)


def write_redirects(redirect_map, out_path):
    """Cloudflare Pages _redirects: 每条 /deals/<id>/ 301 到所属厂商页。
    ::RULE{现有那批 /deals/ 单条优惠页 301 到它所属的那个厂商页}"""
    lines = []
    for src, dst in sorted(redirect_map.items()):
        lines.append("{} {} 301".format(src, dst))
    write(out_path, "\n".join(lines) + "\n")


def build_redirect_map(data):
    """汇总 /deals/ -> /providers/<slug>/ 的映射，两个来源取并集：
    1) data/deal_redirects.json — 抓线上那批 /deals/ 页、从面包屑读出真实
       归属厂商得到的审计表（每条都有出处，不是猜的）
    2) data/offers.json 当前这批优惠按同一算法算出的 deal_id（覆盖新出现的）
    """
    mapping = {}

    audit_path = ROOT / "data" / "deal_redirects.json"
    if audit_path.exists():
        with open(audit_path, "r", encoding="utf-8") as f:
            audit = json.load(f)
        for row in audit:
            src = row.get("deal_path")
            slug = row.get("provider_slug")
            if src and slug:
                mapping[src] = "/providers/" + slug + "/"

    for d in data["deals"]:
        deal_id = slugify(d["title"])[:60] + "-" + str(
            stable_suffix(d["title"] + "|" + d.get("provider_slug", "")))
        pslug = d.get("provider_slug")
        if pslug:
            mapping["/deals/" + deal_id + "/"] = "/providers/" + pslug + "/"

    return mapping


def main():
    cfg = load_cfg()
    data = load_data()
    if data is None:
        print("missing data/offers.json — run scraper.py first", file=sys.stderr)
        sys.exit(1)

    site_cfg = cfg["SITE"]
    brand = site_cfg.get("brand", "vps-deals")
    lang = site_cfg.get("locale", "en-US")
    # domain is the source of truth — it gets auto-suffixed by Cloudflare when
    # the requested name is taken, so users must put the actual deployed URL
    # here, not just "{brand}.pages.dev".
    base_url = "https://" + site_cfg.get("domain", brand + ".pages.dev")
    repo_full = "vps-deals-promo-radar"
    last_fetched = data["generated_at"][:19].replace("T", " ") + " UTC"

    # Ensure site/ exists. Don't bulk-delete: per-file overwrite is safe,
    # and stale orphan pages are pruned only via the workflow's git diff/commit.
    SITE.mkdir(exist_ok=True)

    all_paths = []

    # 1. Index — title/description 由数据生成（厂商数 + 最低价 + 月份）
    _all_prices = [d.get("price") for d in data["deals"] if d.get("price")]
    _cur = next((d.get("currency") for d in data["deals"] if d.get("currency")), "USD")
    _month = None
    if data["deals"] and data["deals"][0].get("fetched_at"):
        try:
            _month = datetime.fromisoformat(
                data["deals"][0]["fetched_at"].replace("Z", "+00:00")).strftime("%B %Y")
        except Exception:
            _month = None
    _idx_title = "VPS Hosting Deals — " + str(len(data["providers"])) + " Providers Compared"
    if _all_prices:
        _idx_title += " from " + money(min(_all_prices), _cur) + "/mo"
    if _month:
        _idx_title += " (" + _month + ")"
    _idx_desc = ("Live public pricing and promotions from " + str(len(data["providers"]))
                 + " VPS hosting providers")
    if _all_prices:
        _idx_desc += ", " + str(len(_all_prices)) + " live offers from " + money(min(_all_prices), _cur) + "/mo"
    if _month:
        _idx_desc += ", updated " + _month
    _idx_desc += ". Refreshed every 6 hours from each provider's own page. Nothing is invented."
    ctx_index = {
        "title": _idx_title,
        "meta_description": _idx_desc,
        "canonical_url": base_url + "/",
        "og_title": brand,
        "og_description": "Live VPS hosting deals, refreshed every 6 hours.",
        "og_type": "website",
        "brand": brand,
        "nav": nav_html("/"),
        "lang": lang,
        "last_fetched_at": last_fetched,
        "repo_full": repo_full,
        "hreflang_tags": "",
    }
    write(SITE / "index.html", render_index(ctx_index, data, cfg, base_url))
    all_paths.append({"path": "", "lastmod": data["generated_at"]})

    # 2. Provider pages
    for p in data["providers"]:
        p_deals = [d for d in data["deals"] if d.get("provider_slug") == p["slug"]]
        p_title, p_desc = provider_page_copy(p, p_deals)
        ctx = dict(ctx_index)
        ctx["title"] = p_title
        ctx["meta_description"] = p_desc
        ctx["canonical_url"] = base_url + "/providers/" + p["slug"] + "/"
        ctx["og_title"] = p_title
        ctx["og_description"] = p_desc
        ctx["og_type"] = "website"
        ctx["nav"] = nav_html("/providers/" + p["slug"] + "/")
        write(SITE / "providers" / p["slug"] / "index.html",
              render_provider(ctx, data, cfg, base_url, p))
        all_paths.append({"path": "providers/" + p["slug"] + "/", "lastmod": p["fetched_at"]})

    # 3. Deal exit — NO new URLs.
    # ::RULE{出口只有一个 优惠进它所属厂商页的动态层 网址数不涨}
    # 单条优惠不再各自开网址。优惠全部落进 render_provider 的 DEAL_TABLE
    # （厂商页动态层）：每次抓取内容变，网址数不变。
    # 历史上已经开出来的那批 /deals/ 页，301 到它所属的厂商页。
    redirect_map = build_redirect_map(data)
    write_redirects(redirect_map, SITE / "_redirects")
    print("  deal pages generated: 0 (offers go to provider-page dynamic layer)")
    print("  301 redirects written:", len(redirect_map))

    # 4. Compare
    _cmp_title = "Compare " + str(len(data["providers"])) + " VPS Providers"
    if _all_prices:
        _cmp_title += " — from " + money(min(_all_prices), _cur) + "/mo"
    if _month:
        _cmp_title += " (" + _month + ")"
    _cmp_desc = "Side-by-side comparison of " + str(len(data["providers"])) + " VPS providers"
    if _month:
        _cmp_desc += ", updated " + _month
    _cmp_desc += ". Live data, refreshed every 6 hours."
    ctx = dict(ctx_index)
    ctx["title"] = _cmp_title
    ctx["meta_description"] = _cmp_desc
    ctx["canonical_url"] = base_url + "/compare/"
    ctx["og_title"] = "Compare VPS providers"
    ctx["og_description"] = ctx["meta_description"]
    ctx["og_type"] = "website"
    ctx["nav"] = nav_html("/compare/")
    write(SITE / "compare" / "index.html",
          render_compare(ctx, data, cfg, base_url))
    all_paths.append({"path": "compare/", "lastmod": data["generated_at"]})

    # 5. sitemap.xml + robots.txt
    write_sitemap(all_paths, SITE / "sitemap.xml", base_url)
    write_robots(SITE / "robots.txt", base_url)

    print("built site/")
    print("  index +", len(data["providers"]), "provider pages + compare + sitemap + robots + _redirects")
    print("  offers rendered into provider-page dynamic layer:", len(data["deals"]))
    print("  sitemap urls:", len(all_paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())