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
        "name": deal["title"],
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
            "name": d["title"],
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
        card = (
            '<div class="deal">'
            '<div class="head">'
            '<h3><a href="/deals/{slug}-{idx}/">{title}</a>{badge}</h3>'
            '<span class="price">{price}</span>'
            '</div>'
            '<div class="meta">From <a href="/providers/{pslug}/">{pname}</a></div>'
            '</div>'
        ).format(
            slug=slugify(d["title"])[:60],
            idx=stable_suffix(d["title"] + "|" + d.get("provider_slug", "")),
            title=e(d["title"]),
            badge=badge,
            price=e(price_label),
            pslug=e(d.get("provider_slug", "")),
            pname=e(d.get("provider_name", "")),
        )
        deal_cards.append(card)
    if not deal_cards:
        deal_cards = ['<div class="deal"><p>No structured deals extracted from the listed providers this run. The scraper only writes entries when it can verify title + price + currency + URL together. If a provider\'s page is unreachable, it\'s listed below as <em>unreachable</em>.</p></div>']

    deal_index = []
    for i, d in enumerate(deals):
        deal_index.append({
            "@type": "ListItem",
            "position": i + 1,
            "url": base_url + "/deals/" + slugify(d["title"])[:60] + "-" + str(stable_suffix(d["title"] + "|" + d.get("provider_slug", ""))) + "/",
            "name": d["title"],
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
        rows = ["<table><thead><tr><th>Title</th><th>Price</th><th>Currency</th><th>Source</th></tr></thead><tbody>"]
        for d in deals:
            url = d.get("offer_url") or d.get("source_url") or "#"
            price_label = ("$" + "{:.2f}".format(d["price"])) if d.get("price") else "—"
            rows.append(
                "<tr><td><a href=\"{offer}\">{title}</a></td><td>{price}</td><td>{cur}</td><td><a href=\"{src}\">source</a></td></tr>".format(
                    offer=e(url), title=e(d["title"]), price=e(price_label),
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


def main():
    cfg = load_cfg()
    data = load_data()
    if data is None:
        print("missing data/offers.json — run scraper.py first", file=sys.stderr)
        sys.exit(1)

    site_cfg = cfg["SITE"]
    brand = site_cfg.get("brand", "vps-deals")
    lang = site_cfg.get("locale", "en-US")
    base_url = "https://" + brand + ".pages.dev"
    repo_full = "vps-deals-promo-radar"
    last_fetched = data["generated_at"][:19].replace("T", " ") + " UTC"

    # Ensure site/ exists. Don't bulk-delete: per-file overwrite is safe,
    # and stale orphan pages are pruned only via the workflow's git diff/commit.
    SITE.mkdir(exist_ok=True)

    all_paths = []

    # 1. Index
    ctx_index = {
        "title": brand + " — current VPS hosting deals",
        "meta_description": "Live public pricing and promotions from " + str(len(data["providers"])) + " VPS hosting providers. Refreshed every 6 hours.",
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
        ctx = dict(ctx_index)
        ctx["title"] = p["name"] + " — VPS deals on " + brand
        ctx["meta_description"] = "Live pricing and promotions from " + p["name"] + ". Source: " + p["source_url"]
        ctx["canonical_url"] = base_url + "/providers/" + p["slug"] + "/"
        ctx["og_title"] = p["name"] + " on " + brand
        ctx["og_description"] = "Live pricing and promotions from " + p["name"] + "."
        ctx["og_type"] = "website"
        ctx["nav"] = nav_html("/providers/" + p["slug"] + "/")
        write(SITE / "providers" / p["slug"] / "index.html",
              render_provider(ctx, data, cfg, base_url, p))
        all_paths.append({"path": "providers/" + p["slug"] + "/", "lastmod": p["fetched_at"]})

    # 3. Deal pages
    for d in data["deals"]:
        deal_id = slugify(d["title"])[:60] + "-" + str(stable_suffix(d["title"] + "|" + d.get("provider_slug", "")))
        ctx = dict(ctx_index)
        ctx["title"] = d["title"] + " — " + brand
        desc = "Live offer from " + d.get("provider_name", "")
        if d.get("price"):
            desc += " at " + str(d["price"]) + " " + d.get("currency", "")
        ctx["meta_description"] = desc
        ctx["canonical_url"] = base_url + "/deals/" + deal_id + "/"
        ctx["og_title"] = d["title"]
        ctx["og_description"] = desc
        ctx["og_type"] = "product"
        ctx["nav"] = nav_html("/deals/" + deal_id + "/")
        write(SITE / "deals" / deal_id / "index.html",
              render_deal(ctx, data, cfg, base_url, d))
        all_paths.append({"path": "deals/" + deal_id + "/", "lastmod": d["fetched_at"]})

    # 4. Compare
    ctx = dict(ctx_index)
    ctx["title"] = "Compare VPS providers — " + brand
    ctx["meta_description"] = "Side-by-side comparison of " + str(len(data["providers"])) + " VPS providers. Live data, refreshed every 6 hours."
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
    print("  index +", len(data["providers"]), "provider pages +", len(data["deals"]), "deal pages + compare + sitemap + robots")
    return 0


if __name__ == "__main__":
    sys.exit(main())