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
import shutil
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
# 厂商 logo：fetch_logos.py 从各家官网抓来存这里，build 只负责拷进站点并引用
LOGO_JSON = ROOT / "data" / "logos.json"
LOGO_DIR = ROOT / "assets" / "logos"
# 0 offers 厂商用真浏览器重取的价：refetch_empty.py 写，build 只读
REFETCH_JSON = ROOT / "data" / "refetch.json"

sys.path.insert(0, str(ROOT))
from scraper import parse_ilang, slugify, MAX_DEALS_PER_PROVIDER, offer_id_for  # reuse the parser


def e(s):
    return html.escape("" if s is None else str(s), quote=True)


def load_data():
    if not DATA.exists():
        return None
    with open(DATA, "r", encoding="utf-8") as f:
        return json.load(f)


def load_articles():
    """读 articles/ 下的文章源文件。

    文件格式: 头部 frontmatter(每行 key: value, 取 title/date/description/gap)
    + 一个空行 + 正文 HTML。slug 取文件名(小写英文短横线)。
    ::RULE{缺任一 frontmatter 字段就报错停下 不许带病发布}"""
    adir = ROOT / "articles"
    if not adir.is_dir():
        return []
    arts = []
    for f in sorted(adir.glob("*.html")):
        slug = f.stem.strip().lower()
        if not re.fullmatch(r"[a-z0-9-]+", slug):
            raise ValueError("article slug must be lowercase alnum/hyphen: " + f.name)
        text = f.read_text(encoding="utf-8")
        head, sep, body = text.partition("\n\n")
        if not sep or not body.strip():
            raise ValueError("article missing frontmatter/body separator: " + f.name)
        meta = {}
        for line in head.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip()
        for req in ("title", "date", "description", "gap"):
            if req not in meta or not meta[req]:
                raise ValueError("article %s missing frontmatter: %s" % (f.name, req))
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", meta["date"]):
            raise ValueError("article %s date must be YYYY-MM-DD" % f.name)
        _updated = meta.get("updated", "").strip()
        if _updated and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", _updated):
            raise ValueError("article %s updated must be YYYY-MM-DD" % f.name)
        arts.append({
            "slug": slug,
            "title": meta["title"],
            "date": meta["date"],
            "updated": _updated,
            "description": meta["description"],
            "gap": meta["gap"],
            "body": body.strip(),
        })
    return arts


def load_cfg():
    return parse_ilang(ILANG_FILE)


def load_refetch(data):
    """读 refetch_empty.py 的产出，返回 (补进来的优惠, 该下线的厂商 slug, 说明)。

    ::RULE{四家 0 offers 的厂商页 取到就写进去 取不到就下线}
    有效性判据不是时间戳，而是「它检查过的厂商集合 == 现在真的 0 offers 的那批」——
    只要集合对得上，结论就还是对的；对不上就宁可不下线，也不拿过期结论动线上。
    """
    have = {d.get("provider_slug") for d in data["deals"]}
    empty_now = {p["slug"] for p in data["providers"] if p["slug"] not in have}
    if not REFETCH_JSON.exists():
        return [], set(), "no refetch.json (run refetch_empty.py) — 不下线"
    with open(REFETCH_JSON, "r", encoding="utf-8") as f:
        doc = json.load(f)
    res = doc.get("results") or {}
    examined = set(res)
    if examined != empty_now:
        return [], set(), ("refetch 检查过的厂商 %s 与现在 0 offers 的 %s 对不上 — 不下线"
                           % (sorted(examined), sorted(empty_now)))
    extra, offline = [], set()
    for slug, rec in res.items():
        if rec.get("status") == "ok" and rec.get("deals"):
            extra.extend(rec["deals"])
        else:
            offline.add(slug)
    return extra, offline, "ok"


def load_template(name):
    return (TEMPLATES / name).read_text(encoding="utf-8")


def fill(template, mapping):
    out = template
    for k, v in mapping.items():
        out = out.replace(k, "" if v is None else str(v))
    return out


def nav_html(active):
    items = [("/", "Home"), ("/compare/", "Compare"), ("/articles/", "Articles")]
    parts = []
    for href, label in items:
        cls = ' class="active"' if active == href else ""
        parts.append('<a href="' + href + '"' + cls + ">" + e(label) + "</a>")
    return "\n".join(parts)


def load_logos():
    """data/logos.json 是 fetch_logos.py 从各厂商官网抓来的结果。
    只认真正存在的文件 —— 抓不到就是抓不到，build 侧回退成首字母，不许拿别的图顶。"""
    if not LOGO_JSON.exists():
        return {}
    with open(LOGO_JSON, "r", encoding="utf-8") as f:
        doc = json.load(f)
    out = {}
    for slug, rec in (doc.get("logos") or {}).items():
        fname = rec.get("logo_file")
        if not fname or not (LOGO_DIR / fname).exists():
            continue
        out[slug] = {"file": fname, "wide": rec.get("status") == "ok_wide"}
    return out


def logo_html(provider, logos, cls="avatar"):
    """厂商头像位：有 logo 就出图，没有就退回首字母。
    ok_wide（横版 logo）加 is-wide，用 contain 缩放不裁切。"""
    rec = logos.get(provider.get("slug", ""))
    if not rec:
        return '<span class="{cls}">{ini}</span>'.format(
            cls=cls, ini=e(initials(provider.get("name", ""))))
    cls = cls + " has-logo" + (" is-wide" if rec["wide"] else "")
    # 不用 loading="lazy"：logo 全是几百字节到十几 KB 的小图，而懒加载会让
    # 首屏以下的那批（compare 表里十几行）一直不渲染 —— 页面看着就是图没了。
    return ('<span class="{cls}">'
            '<img src="/assets/logos/{f}" alt="{name} logo" decoding="async">'
            '</span>').format(cls=e(cls), f=e(rec["file"]), name=e(provider.get("name", "")))


def count_label(n, capped):
    """条数标签。抓取到上限就停，所以到顶的数字是「至少这么多」，
    显示成 12+ —— 不许把被截断的数当精确值报出去。"""
    return str(n) + "+" if capped else str(n)


def is_capped(provider, count):
    """providers 记录里 scraper 会写 deals_capped；老数据没有这个字段时，
    条数正好等于上限就按「被截断」处理（到顶即停，这点是确定的）。"""
    if "deals_capped" in provider:
        return bool(provider["deals_capped"])
    return count >= MAX_DEALS_PER_PROVIDER


def initials(name):
    """厂商名首字母 —— 卡片圆形头像位里的文字（照参考站 site-avatar 的做法）。
    纯展示用的排版元素，不是数据。"""
    words = re.findall(r"[A-Za-z0-9]+", name or "")
    if not words:
        return "?"
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return words[0][:2].upper()


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
    logos = ctx.get("logos") or {}

    # Hero 的三个数字全部来自数据，不是写死的文案
    _prices = [d.get("price") for d in deals if d.get("price")]
    _cur = next((d.get("currency") for d in deals if d.get("currency")), "USD")
    _month = None
    for d in deals:
        if d.get("fetched_at"):
            try:
                _month = datetime.fromisoformat(
                    d["fetched_at"].replace("Z", "+00:00")).strftime("%b %Y")
                break
            except Exception:
                continue
    hero_title = "VPS Hosting Deals & Public Promotions"
    hero_sub = ("Live pricing pulled straight from " + str(len(providers))
                + " hosting providers' own public pages. "
                  "Nothing here is invented; sponsored placements are labeled as such.")

    # Sponsored 联盟广告位：链接只从 .ilang ::MODULE{AFFILIATE} 读（前 2 条），
    # 渲染带 rel="sponsored nofollow noopener"，卡片上标 Sponsored，不许混进普通内容。
    _aff = (cfg.get("AFFILIATE") or [])[:2]
    _aff_cards = []
    for a in _aff:
        _aff_cards.append(
            '<a class="sponsored-card" href="' + e(a["url"]) + '" '
            'rel="sponsored nofollow noopener" target="_blank">'
            '<span class="sponsored-badge">Sponsored</span>'
            '<strong class="sponsored-name">' + e(a["name"]) + "</strong>"
            '<span class="sponsored-desc">' + e(a["blurb"]) + "</span>"
            '<span class="sponsored-cta">Visit site \u2192</span></a>'
        )
    if _aff_cards:
        sponsored_html = (
            '<div class="section-heading"><h2>Sponsored</h2></div>\n'
            '<div class="sponsored-grid">\n' + "\n".join(_aff_cards) + "\n</div>\n"
            '<p class="sponsored-note">Affiliate links: if you buy through one, '
            "we may earn a commission at no extra cost to you.</p>"
        )
    else:
        sponsored_html = ""

    # 厂商卡：圆形头像位 + 名称 + 最低价（照参考站 site-mini-card + site-avatar）
    prov_cards = []
    for p in providers:
        p_deals = [d for d in deals if d.get("provider_slug") == p["slug"]]
        p_prices = [d.get("price") for d in p_deals if d.get("price")]
        p_cur = next((d.get("currency") for d in p_deals if d.get("currency")), "USD")
        p_n = count_label(len(p_deals), is_capped(p, len(p_deals)))
        if p_prices:
            sub = "from " + money(min(p_prices), p_cur) + "/mo · " + p_n + " offers"
        elif p["fetch_status"] == "ok":
            sub = p_n + " offers listed"
        else:
            sub = "unreachable (HTTP " + str(p["http_code"]) + ")"
        prov_cards.append(
            '<li><a class="mini-card" href="/providers/{slug}/">'
            '{logo}'
            '<span class="body">'
            '<span class="name">{name}</span>'
            '<span class="desc">{sub}</span>'
            '</span></a></li>'.format(
                slug=e(p["slug"]), logo=logo_html(p, logos, "avatar"),
                name=e(p["name"]), sub=e(sub))
        )
    provider_links = "\n".join(prov_cards)

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
            badge += ' <span class="badge noprice">no price</span>'
        price_main = money(d.get("price"), d.get("currency")) or "—"
        # ::RULE{deal 卡片必须显示 fetched_at 对应的最后验证时间}
        verified = verified_label(d.get("fetched_at"))
        verified_html = ('<span class="verified">Verified ' + e(verified) + '</span>'
                         if verified else "")
        # ::RULE{出口只有一个} — 卡片指向所属厂商页的动态层，不再开 /deals/ 网址
        # ::RULE{抓坏的字段一律不许留} — 卡片标题由厂商名+价格生成
        # 筛选用 data 属性：data-price 是真实价格（没有就不写），data-provider 是 slug
        prov_url = "/providers/" + e(d.get("provider_slug", "")) + "/"
        data_price = (' data-price="' + e("{:.2f}".format(float(d["price"]))) + '"'
                      if d.get("price") is not None else "")
        card = (
            '<a class="deal-card" href="{purl}" data-provider="{pslug}"{dprice}>'
            '<span class="left">'
            '<span class="title">{label}{badge}</span>'
            '<span class="meta">Go to {pname} deals ›</span>'
            '{verified}'
            '</span>'
            '<span class="price">{price}<span class="cur">{cur}</span></span>'
            '</a>'
        ).format(
            purl=prov_url,
            pslug=e(d.get("provider_slug", "")),
            dprice=data_price,
            label=e(offer_label(d, len(deal_cards) + 1)),
            badge=badge,
            verified=verified_html,
            price=e(price_main),
            cur=e(d.get("currency", "")),
            pname=e(d.get("provider_name", "")),
        )
        deal_cards.append(card)
    if not deal_cards:
        deal_cards = ['<div class="content-card"><p>No structured deals extracted from the listed providers this run. The scraper only writes entries when it can verify price + currency + URL together. If a provider\'s page is unreachable it is marked as such.</p></div>']

    # 筛选器的厂商下拉：只列真实有优惠的厂商，按名称排序
    filter_providers = sorted(
        {d.get("provider_slug"): d.get("provider_name") for d in deals
         if d.get("provider_slug")}.items(),
        key=lambda kv: (kv[1] or "").lower(),
    )
    provider_options = ['<option value="">All providers</option>'] + [
        '<option value="' + e(slug) + '">' + e(name or slug) + "</option>"
        for slug, name in filter_providers
    ]

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
        "{{HERO_TITLE}}": e(hero_title),
        "{{HERO_SUB}}": e(hero_sub),
        "{{UPDATED}}": e(_month or "—"),
        "{{FROM_PRICE}}": e(money(min(_prices), _cur) if _prices else "—"),
        "{{BRAND_DISPLAY}}": e(cfg["SITE"].get("brand", "vps-deals")),
        "{{REPO_FULL}}": e(ctx.get("repo_full", "vps-deals-promo-radar")),
        "{{PROVIDER_COUNT}}": str(len(providers)),
        "{{PROVIDER_LIST}}": provider_links,
        "{{DEAL_COUNT}}": str(len(deals)),
        "{{DEAL_CARDS}}": "\n".join(deal_cards),
        "{{PROVIDER_OPTIONS}}": "\n".join(provider_options),
        "{{SPONSORED}}": sponsored_html,
    })

    jsonld = jsonld_itemlist(deal_index, base_url) if deal_index else ""

    return render_base(ctx, content, jsonld)


def render_provider(ctx, data, cfg, base_url, provider):
    """厂商深评页。只写数据可验证的事实：状态、条数、价格区间、验证时间。
    ::RULE{厂商深评页只写数据可验证的事实} —— 不许星级评分，不许优缺点，
    不许性能/uptime 断言。"""
    slug = provider["slug"]
    logos = ctx.get("logos") or {}
    deals = [d for d in data["deals"] if d.get("provider_slug") == slug]

    # ---- At a glance：全部由真实数据算出 ----
    prices = [d.get("price") for d in deals if d.get("price") is not None]
    cur = next((d.get("currency") for d in deals if d.get("currency")), "USD")
    n_label = count_label(len(deals), is_capped(provider, len(deals)))
    if provider["fetch_status"] == "ok":
        status_html = '<span class="badge">reachable</span> <span class="num">HTTP 200</span>'
    else:
        status_html = ('<span class="badge unreachable">unreachable</span> '
                       '<span class="num">HTTP ' + e(provider["http_code"]) + "</span>")
    if prices:
        price_range = money(min(prices), cur) + "/mo – " + money(max(prices), cur) + "/mo"
        with_price = str(len(prices)) + " of " + str(len(deals))
    else:
        price_range = "—"
        with_price = "0 of " + str(len(deals))
    stats = [
        ("Status", status_html, False),
        ("Offers listed", e(n_label), False),
        ("Price range", e(price_range), False),
        ("With verified price", e(with_price), False),
        ("Last checked", e(provider["fetched_at"][:19].replace("T", " ") + " UTC"), False),
        ("Currency", e(cur), False),
    ]
    stat_grid = "\n".join(
        '<div class="stat"><span class="k">' + k + "</span>"
        '<span class="v">' + (v if not esc else e(v)) + "</span></div>"
        for k, v, esc in stats
    )

    if deals:
        rows = ['<div class="table-wrap"><table><thead><tr>'
                '<th>Offer</th><th>Price</th><th>Currency</th><th>Source</th>'
                '</tr></thead><tbody>']
        for i, d in enumerate(deals, 1):
            url = d.get("offer_url") or d.get("source_url") or "#"
            # ::RULE{抓坏的字段一律不许留} — 行标签由真实字段生成(厂商名+价格)，
            # 不显示 scraper 抓出来的半截原文（如 'Search Multiple Transfer'）。
            label = offer_label(d, i)
            price_label = money(d.get("price"), d.get("currency")) or "—"
            rows.append(
                '<tr><td><a href="{offer}" rel="noopener nofollow">{label}</a></td>'
                '<td class="price-cell num">{price}</td>'
                '<td>{cur}</td>'
                '<td><a href="{src}" rel="noopener nofollow">source</a></td></tr>'.format(
                    offer=e(url), label=e(label), price=e(price_label),
                    cur=e(d.get("currency", "")), src=e(d.get("source_url", ""))
                )
            )
        rows.append("</tbody></table></div>")
        deal_table = "\n".join(rows)
    elif provider["fetch_status"] == "ok":
        deal_table = ('<div class="content-card"><p>Page reachable but no structured deal '
                      'extracted this run. We only write a deal when price + currency + URL '
                      'can all be verified.</p></div>')
    else:
        deal_table = ('<div class="content-card"><p><span class="badge unreachable">unreachable</span> '
                      'HTTP {} — provider page did not return 200. Try again on the next run, '
                      'or check the URL.</p></div>').format(e(provider["http_code"]))

    # ---- 跟踪说明 + FAQ：只写流水线事实 ----
    tracking_info = (
        "<p>Every figure on this page is read from " + e(provider["name"]) +
        "'s own public page (<a href=\"" + e(provider["source_url"]) +
        "\" rel=\"noopener nofollow\">" + e(provider["source_url"]) +
        "</a>) by an automated job that runs every 6 hours. "
        "Nothing is estimated, converted, or written by hand. "
        "The full pipeline is described on the "
        "<a href=\"/methodology/\">methodology page</a>.</p>"
    )
    faqs = [
        ("Where does the pricing data for " + provider["name"] + " come from?",
         "From " + provider["name"] + "'s own public pricing page. Each entry links to "
         "the exact page it was read from via its source link."),
        ("How often is it updated?",
         "Every 6 hours, together with the rest of this site. Each deal card shows "
         "the exact time its entry was last verified."),
        ("Why do some offers show no price?",
         "An offer is published with a price only when price, currency, and URL can "
         "all be verified together. Otherwise it is listed without a price rather "
         "than with a guess."),
        ("Is this a paid placement?",
         "No. No provider can pay to be listed, ranked, or kept on this site."),
    ]
    faq_html = "\n".join(
        "<details><summary>" + e(q) + "</summary><p>" + e(a) + "</p></details>"
        for q, a in faqs
    )

    # ---- 价格历史：2026-10-01 lee 要求隐藏该展示模块。只隐藏渲染；
    # 数据管线 build_price_history 照常运行，data/history.json 继续写，
    # 降价提醒 worker（worker/api.js）每 6 小时还在读它。SVG 图表代码保留，
    # 以后想重新展示时把下面这行改回原来的构建逻辑即可。----
    price_history_html = ""

    content = fill(load_template("provider.html"), {
        "{{CRUMBS}}": crumbs_html([("/", "Home"), ("", e(provider["name"]))]),
        "{{PROVIDER_LOGO}}": logo_html(provider, logos, "avatar p-logo"),
        "{{PROVIDER_NAME}}": e(provider["name"]),
        "{{PROVIDER_URL}}": e(provider["url"]),
        "{{SOURCE_URL}}": e(provider["source_url"]),
        "{{DEAL_COUNT}}": n_label,
        "{{STAT_GRID}}": stat_grid,
        "{{DEAL_TABLE}}": deal_table,
        "{{TRACKING_INFO}}": tracking_info,
        "{{FAQ}}": faq_html,
        "{{PRICE_HISTORY}}": price_history_html,
        "{{LAST_FETCHED_AT}}": e(provider["fetched_at"][:19].replace("T", " ") + " UTC"),
    })

    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@graph": [
            json.loads(jsonld_service(provider, deals, base_url)),
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {"@type": "Question", "name": q,
                     "acceptedAnswer": {"@type": "Answer", "text": a}}
                    for q, a in faqs
                ],
            },
        ],
    }, ensure_ascii=False)

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
    logos = ctx.get("logos") or {}
    rows = []
    for p in data["providers"]:
        deals_for_p = [d for d in data["deals"] if d.get("provider_slug") == p["slug"]]
        status = ('<span class="badge">reachable</span>' if p["fetch_status"] == "ok"
                  else '<span class="badge unreachable">unreachable</span>')
        badge_cls = "" if p["fetch_status"] == "ok" else "unreachable"
        rows.append(
            '<tr><td><a class="cell-provider" href="/providers/{slug}/">'
            '{logo}<span>{name}</span></a></td>'
            '<td><span class="badge {bcls}">{status}</span> <span class="num">HTTP {code}</span></td>'
            '<td class="num">{n}</td>'
            '<td><a href="{src}" rel="noopener nofollow">source</a></td></tr>'.format(
                slug=e(p["slug"]), name=e(p["name"]), bcls=badge_cls,
                logo=logo_html(p, logos, "avatar t-logo"),
                status="reachable" if p["fetch_status"] == "ok" else "unreachable",
                code=e(p["http_code"]),
                n=count_label(len(deals_for_p), is_capped(p, len(deals_for_p))),
                src=e(p["source_url"])
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


def render_black_friday(ctx, data, cfg, base_url):
    """Black Friday 2026 专题页。
    ::RULE{Black Friday 页的日期 2026-11-27 是真实日历事实；暂无 BF 专项优惠时如实写}
    页面内容全部来自真实数据：倒计时目标是 I-Lang 里声明的真实日期；
    BF 专项优惠按标题含 black friday 检出（当前为 0 就如实写 0）；
    「当前最低价」是全站真实价格排序的前 15。"""
    bf_date = (cfg.get("RENDER") or {}).get("black_friday_date", "2026-11-27").strip()
    try:
        bf_label = datetime.fromisoformat(bf_date).strftime("%B %d, %Y")
    except Exception:
        bf_label = bf_date

    # BF 专项优惠：标题里明确写 black friday 的才算，不许从普通优惠里挑
    bf_deals = [d for d in data["deals"]
                if "black friday" in (d.get("title") or "").lower()]
    if bf_deals:
        bf_block = ('<div class="content-card"><p><strong>' + str(len(bf_deals)) +
                    "</strong> Black Friday offers published by tracked providers:</p></div>")
    else:
        bf_block = ('<div class="content-card"><p>No Black Friday–specific offers have been '
                    "published by the tracked providers yet. This page rebuilds every 6 hours — "
                    "anything a provider publishes will show up here on the next refresh.</p></div>")

    # 当前全站最低价 top 15（真实价格排序）
    priced = sorted(
        [d for d in data["deals"] if d.get("price") is not None],
        key=lambda d: float(d["price"]),
    )[:15]
    rows = []
    for i, d in enumerate(priced, 1):
        url = d.get("offer_url") or d.get("source_url") or "#"
        rows.append(
            '<tr><td class="num">' + str(i) + "</td>"
            '<td><a href="/providers/' + e(d.get("provider_slug", "")) + '/">' +
            e(d.get("provider_name", "")) + "</a></td>"
            '<td><a href="' + e(url) + '" rel="noopener nofollow">' +
            e(offer_label(d, i)) + "</a></td>"
            '<td class="price-cell num">' + e(money(d.get("price"), d.get("currency")) or "—") +
            "</td></tr>"
        )
    cheap_table = (
        '<div class="table-wrap"><table><thead><tr><th>#</th><th>Provider</th>'
        "<th>Offer</th><th>Price</th></tr></thead><tbody>\n" +
        "\n".join(rows) + "\n</tbody></table></div>"
    ) if rows else '<div class="content-card"><p>No priced offers right now.</p></div>'

    countdown_js = (
        "<script>(function(){"
        "var target=new Date('" + e(bf_date) + "T00:00:00Z').getTime();"
        "var el=document.getElementById('bf-countdown');"
        "if(!el||isNaN(target))return;"
        "function tick(){"
        "var diff=target-Date.now();"
        "if(diff<=0){el.textContent='Black Friday is here — check the offers below.';return;}"
        "var d=Math.floor(diff/864e5),h=Math.floor(diff%864e5/36e5),"
        "m=Math.floor(diff%36e5/6e4),s=Math.floor(diff%6e4/1e3);"
        "el.textContent=d+'d '+h+'h '+m+'m '+s+'s';"
        "}"
        "tick();setInterval(tick,1000);"
        "})();</script>"
    )

    content = fill(load_template("black-friday.html"), {
        "{{CRUMBS}}": crumbs_html([("/", "Home"), ("", "Black Friday 2026")]),
        "{{BF_DATE_LABEL}}": e(bf_label),
        "{{BF_DEAL_COUNT}}": str(len(bf_deals)),
        "{{BF_DEAL_BLOCK}}": bf_block,
        "{{CHEAP_TABLE}}": cheap_table,
        "{{COUNTDOWN_JS}}": countdown_js,
        "{{PROVIDER_COUNT}}": str(len(data["providers"])),
    })

    itemlist = []
    for i, d in enumerate(priced):
        itemlist.append({
            "@type": "ListItem",
            "position": i + 1,
            "url": base_url + "/providers/" + d.get("provider_slug", "") + "/",
            "name": d.get("provider_name", "") + " — " + (money(d.get("price"), d.get("currency")) or ""),
        })
    jsonld = jsonld_itemlist(itemlist, base_url) if itemlist else ""
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


def verified_label(fetched_at):
    """deal 卡片的「最后验证时间」—— 直接来自 fetched_at 的绝对时间。
    解析失败或缺失就返回 None（调用方不显示），不许编一个。"""
    if not fetched_at:
        return None
    try:
        dt = datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00"))
    except Exception:
        return None
    return dt.strftime("%b %d, %Y %H:%M UTC")


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

    n_label = count_label(len(deals), is_capped(provider, len(deals)))
    desc = name + " VPS hosting deals and public pricing, updated"
    if month:
        desc += " " + month
    desc += "."
    if prices:
        desc += " " + n_label + " live offers from " + money(min(prices), cur) + "/mo."
    else:
        desc += " " + n_label + " live offers listed."
    desc += " Nothing here is invented — every figure comes from " + name + "'s own public page."

    return title, desc


def render_404(ctx, data, cfg, base_url):
    """真 404 页。Cloudflare Pages 对任何没匹配上的路径都会拿 /404.html 当响应体
    并回 404 状态码 —— 前提是站点根上真有这个文件。这里不配任何 catch-all 规则，
    所以不存在路径不会被兜底成 200 的首页。"""
    content = fill(load_template("404.html"), {
        "{{CRUMBS}}": crumbs_html([("/", "Home"), ("", "404")]),
        "{{PROVIDER_COUNT}}": str(len(data["providers"])),
        "{{DEAL_COUNT}}": str(len(data["deals"])),
    })
    return render_base(ctx, content, "{}")


def render_legal(ctx, data, cfg, base_url, tpl_name, crumb_label):
    """隐私政策 / 关于 / 联系 三页共用一个渲染器。
    这三个页面的正文是固定的说明文字，只替换厂商数、联系邮箱、修订日期、仓库地址 ——
    没有任何一个数字是从别处推出来的。"""
    content = fill(load_template(tpl_name), {
        "{{CRUMBS}}": crumbs_html([("/", "Home"), ("", crumb_label)]),
        "{{LAST_UPDATED}}": e(ctx.get("legal_updated", "")),
        "{{CONTACT_EMAIL}}": e(ctx.get("contact_email", "")),
        "{{BRAND_DISPLAY}}": e(ctx.get("brand_display", ctx["brand"])),
        "{{PROVIDER_COUNT}}": str(len(data["providers"])),
    })
    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "ContactPage" if tpl_name == "contact.html" else "WebPage",
        "url": ctx["canonical_url"],
        "name": ctx["title"],
        "inLanguage": ctx["lang"],
        "isPartOf": {"@type": "WebSite", "url": base_url + "/"},
    }, ensure_ascii=False)
    return render_base(ctx, content, jsonld)


def render_article(ctx, data, cfg, base_url, article):
    """单篇内容页。正文 HTML 由作者手写，build 只做转义安全的字段替换；
    价格/日期类断言的真实性由 I-Lang ::MODULE{ARTICLES} 约束，build 不校验内容真伪。"""
    _date_line = ""
    if article.get("date"):
        _date_line = '<p class="article-date">Published ' + e(article["date"])
        if article.get("updated"):
            _date_line += " · Updated " + e(article["updated"])
        _date_line += "</p>"
    _body = article["body"]
    # 移动端防溢出：正文里的 <table> 统一包进 .table-wrap（CSS 在 ≤720px 给它
    # overflow-x:auto），避免宽表把 375px 页面撑破。body 是手写源文件，
    # 不是上次构建产物，不会重复包裹；已包过的跳过。
    if "<table" in _body and "table-wrap" not in _body:
        _body = re.sub(r"<table(\s[^>]*)?>", r'<div class="table-wrap"><table\1>', _body)
        _body = _body.replace("</table>", "</table></div>")
    # 结构自检：正文 <div> 开闭必须平衡。多余的 </div> 会被浏览器拿去提前
    # 关掉外层的 .wrap 布局容器，导致其后所有内容全屏贴边（2026-10-01 真实
    # 事故：误补 </div> 造成手机端文章文字贴边）。不平衡直接让构建失败，
    # 不许悄悄上线。
    if len(re.findall(r"<div(?=[\s>])", _body)) != _body.count("</div>"):
        raise SystemExit(
            "build failed: unbalanced <div> in article '%s' (opens=%d closes=%d)"
            % (article.get("slug", "?"),
               len(re.findall(r"<div(?=[\s>])", _body)), _body.count("</div>")))
    content = fill(load_template("article.html"), {
        "{{CRUMBS}}": crumbs_html([("/", "Home"), ("/articles/", "Articles"), ("", article["title"])]),
        "{{ARTICLE_DATE_LINE}}": _date_line,
        "{{ARTICLE_BODY}}": _body,
    })
    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "Article",
        "url": ctx["canonical_url"],
        "headline": article["title"],
        "description": article["description"],
        **({"datePublished": article["date"]} if article.get("date") else {}),
        **({"dateModified": article["updated"]} if article.get("updated") else {}),
        "inLanguage": ctx["lang"],
        "isPartOf": {"@type": "WebSite", "url": base_url + "/"},
    }, ensure_ascii=False)
    return render_base(ctx, content, jsonld)


def render_base(ctx, content_html, jsonld_text):
    base = load_template("_base.html")
    subs = {
        "{{TITLE}}": e(ctx["title"]),
        "{{META_DESCRIPTION}}": e(ctx["meta_description"]),
        "{{CANONICAL_URL}}": e(ctx["canonical_url"]),
        "{{ROBOTS_META}}": ctx.get("robots_meta", ""),
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
        "{{GA4_TAG}}": ctx.get("ga4_tag", ""),
        "{{CSS_VER}}": ctx.get("css_ver", ""),
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


HISTORY_JSON = ROOT / "data" / "history.json"


def deal_history_key(d):
    """价格历史的身份键。优先用抓取时算好的 offer_id；旧快照没有 offer_id
    就用 scraper.offer_id_for 按完全相同的归一化补算 —— 同一个函数，
    新旧快照的键必然一致。价格永远不进键（要追的就是价格变化）。"""
    oid = d.get("offer_id")
    if oid:
        return str(oid)
    return offer_id_for(d.get("provider_slug"), d.get("offer_url"), d.get("title"))


def build_price_history(data, cfg):
    """构建时生成价格历史（::RULE{history_source} ::RULE{价格历史只记录真实快照的价格变动点}）。

    数据源 = git 里 data/offers.json 的快照链 + 工作区当前快照（update.yml 里
    scraper 刚抓完还没提交的那一份）。只记录真实的价格变动点（delta 编码，
    含首点）；快照里没出现就是没出现，不插值、不编造。
    结果写 data/history.json 并提交入库 —— shallow checkout（deploy.yml）
    时 git 链太短，就用它当回退底座继续追加。
    快照不足 2 个返回 None：调用方不渲染历史区块，而不是画一张假图。

    已知数据质量问题（2026-09-28 实测）：UpCloud 10 条 deal 级序列呈严格
    交替振荡（如 6↔7），是 scraper 正则在同一页面交替抓到两个不同数字，
    不是真实调价。厂商级 min 序列不受影响（UpCloud min 为干净的 $3.0
    平直线）。Phase 4 做降价提醒时必须加"连续两次快照确认"去抖，
    不能直接拿 deal 级变动点触发。
    """
    render_cfg = cfg.get("RENDER") or {}
    if str(render_cfg.get("price_history", "")).lower() != "true":
        return None

    import subprocess

    def git(*args):
        r = subprocess.run(["git", "-C", str(ROOT)] + list(args),
                           capture_output=True, text=True, timeout=120)
        return r.stdout if r.returncode == 0 else None

    snapshots = []  # [(generated_at, deals)]
    log = git("log", "--format=%H%x00%aI", "--reverse", "--", "data/offers.json")
    if log:
        for line in log.strip().split("\n"):
            sha, _, _ad = line.partition("\x00")
            blob = git("show", sha + ":data/offers.json")
            if not blob:
                continue
            try:
                doc = json.loads(blob)
            except Exception:
                continue
            snapshots.append((doc.get("generated_at") or _ad, doc.get("deals") or []))
    # 工作区当前快照：update.yml 里它是刚抓完未提交的新数据
    wt_gen = data.get("generated_at") or ""
    if not snapshots or snapshots[-1][0] != wt_gen:
        snapshots.append((wt_gen, data.get("deals") or []))

    if len(snapshots) < 2:
        # 回退：用已提交的 history.json 当底座，把当前快照追加进去
        base = None
        if HISTORY_JSON.exists():
            try:
                base = json.loads(HISTORY_JSON.read_text(encoding="utf-8"))
            except Exception:
                base = None
        if not base or not base.get("deal_series"):
            return None
        pts = {}
        for d in data.get("deals") or []:
            if d.get("price") is None:
                continue
            try:
                price = float(d["price"])
            except (TypeError, ValueError):
                continue
            pts[deal_history_key(d)] = (d.get("fetched_at") or wt_gen, price, d)
        changed = _append_points(base, pts, wt_gen, provider_delta=False)
        if changed:
            base["meta"]["built_at"] = datetime.now(timezone.utc).isoformat()
            HISTORY_JSON.write_text(json.dumps(base, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
        return base

    deal_series = {}
    provider_min = {}
    for gen_at, deals in snapshots:
        pts = {}
        for d in deals:
            if d.get("price") is None:
                continue
            try:
                price = float(d["price"])
            except (TypeError, ValueError):
                continue
            ts = d.get("fetched_at") or gen_at or ""
            pts[deal_history_key(d)] = (ts, price, d)
        _append_points({"deal_series": deal_series, "provider_min": provider_min},
                       pts, gen_at, provider_delta=False)

    #  series 太稀疏（全站 <2 个变动点）就不渲染
    total_points = sum(len(s["points"]) for s in deal_series.values())
    history = {
        "meta": {
            "snapshots": len(snapshots),
            "since": snapshots[0][0],
            "until": snapshots[-1][0],
            "built_at": datetime.now(timezone.utc).isoformat(),
            "source": "git log -- data/offers.json",
        },
        "deal_series": deal_series,
        "provider_min": provider_min,
    }
    if total_points < 2:
        return None
    HISTORY_JSON.write_text(json.dumps(history, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print("  price history: snapshots=%d deals_tracked=%d points=%d" %
          (len(snapshots), len(deal_series), total_points))
    return history


def _append_points(history, pts, gen_at, provider_delta=True):
    """把一个快照的点并入 series。
    deal 级别：只在价格变化时追加（含首点）—— 省空间。
    厂商最低价：默认同样 delta；传 provider_delta=False 则每个快照都记一个点，
      这样价格从没动过的厂商也能画出一条如实的平直线（"N 次检查无变动"）。
    同一时间戳重复出现则后值覆盖前值。返回是否发生变化。"""
    changed = False
    deal_series = history["deal_series"]
    provider_min = history["provider_min"]
    for key, (ts, price, d) in pts.items():
        s = deal_series.get(key)
        if s is None:
            s = deal_series[key] = {
                "provider_slug": d.get("provider_slug"),
                "provider_name": d.get("provider_name"),
                "title": d.get("title"),
                "url": d.get("offer_url") or d.get("source_url"),
                "currency": d.get("currency"),
                "first_seen": ts,
                "points": [],
            }
        points = s["points"]
        if points and points[-1][0] == ts:
            if points[-1][1] != price:
                points[-1][1] = price
                changed = True
        elif not points or points[-1][1] != price:
            points.append([ts, price])
            changed = True
    # 每家厂商当次快照的最低价（只看带真实价格的 deal）
    per_provider = {}
    for key, (ts, price, d) in pts.items():
        slug = d.get("provider_slug")
        if not slug:
            continue
        if slug not in per_provider or price < per_provider[slug][0]:
            per_provider[slug] = (price, ts, d.get("currency"))
    for slug, (price, ts, cur) in per_provider.items():
        s = provider_min.get(slug)
        if s is None:
            s = provider_min[slug] = {"currency": cur, "points": []}
        points = s["points"]
        if points and points[-1][0] == gen_at:
            if points[-1][1] != price:
                points[-1][1] = price
                changed = True
        elif not points or not provider_delta or points[-1][1] != price:
            points.append([gen_at, price])
            changed = True
    return changed


def svg_price_chart(points, currency, label):
    """纯服务端 SVG 折线图，零 JS。points=[[ts_iso, price],...] 已按时间排序。
    x 按真实时间戳定位（快照间隔不均匀也不撒谎）；y 按价格区间缩放。
    少于 2 个点返回空字符串 —— 调用方不渲染区块。"""
    if len(points) < 2:
        return ""
    W, H = 560, 190
    PL, PR, PT, PB = 46, 10, 12, 26
    iw, ih = W - PL - PR, H - PT - PB

    def ts(s):
        try:
            return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    xs = [ts(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    if x1 == x0:
        x1 = x0 + 1
    if y1 == y0:
        y0, y1 = y0 * 0.95, y1 * 1.05 or 1

    def X(t):
        return PL + (t - x0) / (x1 - x0) * iw

    def Y(v):
        return PT + (1 - (v - y0) / (y1 - y0)) * ih

    path = "M" + " L".join("%.1f,%.1f" % (X(t), Y(v)) for t, v in zip(xs, ys))
    dots = "".join(
        '<circle cx="%.1f" cy="%.1f" r="3" fill="#1677ff"><title>%s: %s</title></circle>'
        % (X(t), Y(v), e(fmt_date(p[0])), e(money(v, currency)))
        for (t, v), p in zip(zip(xs, ys), points)
    )
    sym = {"USD": "$", "EUR": "€", "GBP": "£"}.get((currency or "USD").upper(), "")
    out = [
        '<svg class="price-chart" viewBox="0 0 %d %d" role="img" aria-label="%s">' % (W, H, e(label)),
        '<path d="%s" fill="none" stroke="#1677ff" stroke-width="2"/>' % path,
        dots,
        '<text x="%d" y="%d" class="pc-lbl">%s%.2f</text>' % (PL, PT - 2, sym, y1),
        '<text x="%d" y="%d" class="pc-lbl">%s%.2f</text>' % (PL, H - 8, sym, y0),
        '<text x="%d" y="%d" class="pc-lbl pc-r">%s</text>' % (W - PR, H - 8, e(fmt_date(points[0][0]))),
        '<text x="%d" y="%d" class="pc-lbl">%s</text>' % (PL, H - 8, e(fmt_date(points[-1][0]))),
        "</svg>",
    ]
    return "\n".join(out)


def fmt_date(ts_iso):
    try:
        return datetime.fromisoformat(str(ts_iso).replace("Z", "+00:00")).strftime("%b %d")
    except Exception:
        return str(ts_iso)[:10]


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
    repo_full = "Ltaimao/vps-deals-promo-radar"
    last_fetched = data["generated_at"][:19].replace("T", " ") + " UTC"
    # 联系邮箱来自 site.ilang 的 @CONTACT。它必须是一个真能收信的地址 ——
    # 挂一个收不到信的邮箱等于在页面上写一句假话，所以这里只读配置，不兜底编一个。
    contact_email = site_cfg.get("email", "")
    if not contact_email:
        print("missing ::STATE{@CONTACT, email:...} in .ilang/site.ilang", file=sys.stderr)
        sys.exit(1)
    if not re.match(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", contact_email, re.I):
        print("contact email looks malformed:", contact_email, file=sys.stderr)
        sys.exit(1)
    legal_updated = site_cfg.get("legal_updated", "")

    # GA4 标签：衡量 ID 只从 .ilang ::MODULE{ANALYTICS} 读（I-Lang RULE），
    # 这里拼好整段标签，模板里只放 {{GA4_TAG}} 占位符，不许手写 ID。
    _analytics = cfg.get("ANALYTICS", {})
    _ga4_id = _analytics.get("ga4_measurement_id", "").strip()
    if _analytics.get("ga4_enabled") == "true" and _ga4_id:
        ga4_tag = (
            '<script async src="https://www.googletagmanager.com/gtag/js?id='
            + _ga4_id + '"></script>\n'
            '<script>\nwindow.dataLayer = window.dataLayer || [];\n'
            'function gtag(){dataLayer.push(arguments);}\n'
            'gtag("js", new Date());\n'
            'gtag("config", "' + _ga4_id + '");\n</script>'
        )
    else:
        ga4_tag = ""

    # Ensure site/ exists. Don't bulk-delete: per-file overwrite is safe,
    # and stale orphan pages are pruned only via the workflow's git diff/commit.
    SITE.mkdir(exist_ok=True)

    # 0a. 0 offers 的厂商：把真浏览器重取到的价并进数据；取不到的把该页下线。
    extra_deals, offline_slugs, refetch_note = load_refetch(data)
    if extra_deals:
        data["deals"] = data["deals"] + extra_deals
    offline_providers = [p for p in data["providers"] if p["slug"] in offline_slugs]
    if offline_providers:
        # 从渲染集合里摘掉 —— index 卡片 / compare 表 / sitemap 三处一起跟着消失
        data["providers"] = [p for p in data["providers"] if p["slug"] not in offline_slugs]
    print("  refetch:", refetch_note,
          "| 补进优惠", len(extra_deals),
          "| 下线厂商", len(offline_providers),
          [p["slug"] for p in offline_providers])

    # 0a2. 价格历史 —— git 快照链重建，只记真实变动点；写 data/history.json 入库。
    #      快照不足时返回 None，厂商页直接不渲染该区块（不画假图）。
    history = build_price_history(data, cfg)

    # 0b. 厂商 logo —— fetch_logos.py 抓来的图拷进站点 /assets/logos/，
    #    渲染时按 slug 查表；抓不到的厂商保持首字母色块，不拿别的图顶替。
    logos = load_logos()
    if logos:
        logo_dir = SITE / "assets" / "logos"
        logo_dir.mkdir(parents=True, exist_ok=True)
        want = set()
        for _rec in logos.values():
            shutil.copyfile(LOGO_DIR / _rec["file"], logo_dir / _rec["file"])
            want.add(_rec["file"])
        # 站点目录是整份部署上去的，旧图不清掉就会一直挂在线上（虽然没人引用）
        stale = [f.name for f in logo_dir.iterdir()
                 if f.is_file() and f.name not in want]
        for name in stale:
            (logo_dir / name).unlink()
        if stale:
            print("  清掉站点里过期的 logo:", len(stale), sorted(stale)[:6])
    # 只按「当前在线的厂商」算，否则下线的厂商（logo 还留在 logos.json 里）
    # 会把这个比例撑好看 —— 报数就得报线上真实有多少个头像位有图。
    with_logo = [p["slug"] for p in data["providers"] if p["slug"] in logos]
    no_logo = [p["slug"] for p in data["providers"] if p["slug"] not in logos]
    print("  provider logos:", len(with_logo), "/", len(data["providers"]),
          "(回退首字母:", ", ".join(no_logo) or "无", ")")

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
    # 样式表缓存击穿：site.css 内容哈希拼在 URL 上（?v=），以后改 CSS
    # 用户浏览器/中间缓存会立即取新版，不用等 max-age 过期。哈希取自
    # templates/site.css —— 第 5 步拷到站点的就是这个文件。
    css_ver = hashlib.md5((TEMPLATES / "site.css").read_bytes()).hexdigest()[:8]
    ctx_index = {
        "css_ver": css_ver,
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
        "contact_email": contact_email,
        "legal_updated": legal_updated,
        "ga4_tag": ga4_tag,
        "brand_display": brand,
        "hreflang_tags": "",
        "logos": logos,
        "history": history,
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

    # 2b. 下线厂商的旧目录：本地 site/ 是增量覆盖的，被下线的页会留在盘上；
    #     CI 每次全新 checkout 构建所以没这个问题。这里只报告，删除由人确认。
    stale_dirs = []
    if (SITE / "providers").exists():
        for d in sorted((SITE / "providers").iterdir()):
            if d.is_dir() and d.name not in {p["slug"] for p in data["providers"]}:
                stale_dirs.append(str(d.relative_to(SITE)))
    if stale_dirs:
        print("  stale provider dirs on disk (需人工确认后删):", stale_dirs)

    # 3. Deal exit — NO new URLs.
    # ::RULE{出口只有一个 优惠进它所属厂商页的动态层 网址数不涨}
    # 单条优惠不再各自开网址。优惠全部落进 render_provider 的 DEAL_TABLE
    # （厂商页动态层）：每次抓取内容变，网址数不变。
    # 历史上已经开出来的那批 /deals/ 页，301 到它所属的厂商页。
    # ::RULE{老的单条优惠地址按映射表逐条 301 一条都不许漏}
    # ::RULE{映射表里没有目标的让它 404 —— 不许 301 到一个不存在的页}
    live_slugs = {p["slug"] for p in data["providers"]}
    redirect_map = build_redirect_map(data)
    dropped = {s: d for s, d in redirect_map.items()
               if d.strip("/").split("/")[-1] not in live_slugs}
    for s in dropped:
        del redirect_map[s]
    # 被下线的厂商页：老地址 301 回它的上位页（首页），不留死链
    for p in offline_providers:
        redirect_map["/providers/" + p["slug"] + "/"] = "/"
    write_redirects(redirect_map, SITE / "_redirects")
    print("  deal pages generated: 0 (offers go to provider-page dynamic layer)")
    print("  301 redirects written:", len(redirect_map),
          "(映射表里目标页不存在的", len(dropped), "条已剔出 -> 它们返回 404)")
    if dropped:
        for s, d in sorted(dropped.items()):
            print("     404  ", s, "-> 目标页不存在:", d)
    if offline_providers:
        for p in offline_providers:
            print("     301  /providers/{}/ -> / (该页已下线)".format(p["slug"]))

    # 4b. 真 404 页 —— 站点根上必须有 404.html，Pages 才会拿它当未匹配路径的响应体
    ctx404 = dict(ctx_index)
    ctx404["title"] = "404 — page not found"
    ctx404["meta_description"] = "This URL does not exist on vpsdealswire.com."
    ctx404["canonical_url"] = base_url + "/404.html"
    ctx404["og_title"] = ctx404["title"]
    ctx404["og_description"] = ctx404["meta_description"]
    ctx404["nav"] = nav_html("")
    ctx404["robots_meta"] = '<meta name="robots" content="noindex">'
    write(SITE / "404.html", render_404(ctx404, data, cfg, base_url))

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

    # 4c. Black Friday 2026 专题页 —— 日期是 I-Lang 里声明的真实日历事实，
    #     内容全部来自真实数据；暂无 BF 专项优惠时如实写暂无。
    _bf_title = "Black Friday VPS Deals 2026 — " + str(len(data["providers"])) + " Providers"
    if _all_prices:
        _bf_title += " from " + money(min(_all_prices), _cur) + "/mo"
    _bf_desc = ("Black Friday 2026 VPS deals (" +
                (cfg.get("RENDER") or {}).get("black_friday_date", "2026-11-27").strip() +
                "), verified from each provider's own page and refreshed every 6 hours.")
    c = dict(ctx_index)
    c["title"] = _bf_title
    c["meta_description"] = _bf_desc
    c["canonical_url"] = base_url + "/black-friday/"
    c["og_title"] = "Black Friday VPS Deals 2026"
    c["og_description"] = _bf_desc
    c["og_type"] = "website"
    c["nav"] = nav_html("")
    write(SITE / "black-friday" / "index.html",
          render_black_friday(c, data, cfg, base_url))
    all_paths.append({"path": "black-friday/", "lastmod": data["generated_at"]})

    # 4b. 隐私政策 / 关于 / 联系 / 方法论 —— 必备页。页脚链接指向它们，
    # 一起进 sitemap。正文里没有任何编造的资质、公司名或邮箱。
    legal_pages = (
        ("privacy.html", "privacy", "Privacy",
         "Privacy policy — what this site does with data",
         "What this site collects (nothing that identifies you), why it sets no cookies, "
         "how affiliate links would work if we add them, and how third-party ads "
         "will be disclosed before the first one goes live."),
        ("about.html", "about", "About",
         "About this site — who runs it and how the numbers are made",
         "An independent VPS price tracker run by a single publisher. How a provider gets "
         "listed, how every price is read from the provider's own page, and what this site is not."),
        ("contact.html", "contact", "Contact",
         "Contact — " + contact_email,
         "The one way to reach this site is email: " + contact_email
         + ". What to write about, and what the provider has to handle instead."),
        ("methodology.html", "methodology", "Methodology",
         "Methodology — how every number on this site is made",
         "The exact pipeline behind this site: where the data comes from, what is extracted "
         "per offer, the quality rules, and what this site never does."),
    )
    for tpl_name, slug, crumb, title, desc in legal_pages:
        c = dict(ctx_index)
        c["title"] = title
        c["meta_description"] = desc
        c["canonical_url"] = base_url + "/" + slug + "/"
        c["og_title"] = title
        c["og_description"] = desc
        c["og_type"] = "website"
        c["nav"] = nav_html("")   # 三页不进主导航，从页脚进
        write(SITE / slug / "index.html",
              render_legal(c, data, cfg, base_url, tpl_name, crumb))
        all_paths.append({"path": slug + "/",
                          "lastmod": legal_updated or data["generated_at"]})

    # 4d. 内容文章页 —— articles/*.html，每篇渲染到 /articles/<slug>/，进 sitemap；
    #     另生成 /articles/ 索引页。见 .ilang ::MODULE{ARTICLES}。
    articles = load_articles()
    for a in articles:
        c = dict(ctx_index)
        c["title"] = a["title"]
        c["meta_description"] = a["description"]
        c["canonical_url"] = base_url + "/articles/" + a["slug"] + "/"
        c["og_title"] = a["title"]
        c["og_description"] = a["description"]
        c["og_type"] = "article"
        c["nav"] = nav_html("")
        write(SITE / "articles" / a["slug"] / "index.html",
              render_article(c, data, cfg, base_url, a))
        all_paths.append({"path": "articles/" + a["slug"] + "/",
                          "lastmod": a["date"]})
    if articles:
        _idx_rows = []
        for a in sorted(articles, key=lambda x: x["date"], reverse=True):
            _idx_rows.append(
                '<div class="content-card"><p class="article-date">Published ' + e(a["date"]) + '</p>'
                + '<h2><a href="/articles/' + a["slug"] + '/">' + e(a["title"]) + '</a></h2>'
                + '<p>' + e(a["description"]) + '</p></div>')
        _idx_article = {
            "slug": "index", "title": "Articles", "date": "",
            "description": "Hands-on VPS buying guides with live-checked prices.",
            "gap": "index",
            "body": "\n".join(_idx_rows),
        }
        c = dict(ctx_index)
        c["title"] = "Articles — " + ctx_index["brand"]
        c["meta_description"] = "Hands-on VPS buying guides. Every price live-checked from the provider's own page."
        c["canonical_url"] = base_url + "/articles/"
        c["og_title"] = c["title"]
        c["og_description"] = c["meta_description"]
        c["og_type"] = "website"
        c["nav"] = nav_html("")
        write(SITE / "articles" / "index.html",
              render_article(c, data, cfg, base_url, _idx_article))
        all_paths.append({"path": "articles/",
                          "lastmod": max(a["date"] for a in articles)})
    # 4e. 文章配图 —— static/articles/<slug>.png 拷到 site/articles/<slug>.png
    #     （正文引用 /articles/<slug>.png；5c 的 static/ 根拷贝不进子目录，这里单独处理；
    #     见 .ilang ::MODULE{ARTICLES} 配图规则）
    _art_img_src = ROOT / "static" / "articles"
    if _art_img_src.is_dir():
        (SITE / "articles").mkdir(parents=True, exist_ok=True)
        for _img in sorted(_art_img_src.glob("*.png")):
            if _img.is_file():
                shutil.copyfile(_img, SITE / "articles" / _img.name)
    print("  articles rendered:", len(articles))

    # 5. 样式表 —— 从 templates/ 拷到站点根，页面用 /site.css 引它
    css_src = TEMPLATES / "site.css"
    if css_src.exists():
        write(SITE / "site.css", css_src.read_text(encoding="utf-8"))

    # 5b. 品牌资产 —— assets/brand/ 的 logo.svg / icon.svg / favicon.ico /
    #     apple-touch-icon.png 拷到站点根（_base.html 的 head 引用它们）
    brand_src = ROOT / "assets" / "brand"
    for _name in ("logo.svg", "icon.svg", "favicon.ico", "apple-touch-icon.png"):
        _src = brand_src / _name
        if _src.exists():
            shutil.copyfile(_src, SITE / _name)

    # 5c. 根目录静态文件 —— static/ 下的所有文件原样拷到站点根
    #     （第三方平台的 HTML 所有权验证文件放这里，build 才会带上部署）
    static_src = ROOT / "static"
    if static_src.is_dir():
        for _src in sorted(static_src.iterdir()):
            if _src.is_file() and not _src.name.startswith("."):
                shutil.copyfile(_src, SITE / _src.name)

    # 6. sitemap.xml + robots.txt
    write_sitemap(all_paths, SITE / "sitemap.xml", base_url)
    write_robots(SITE / "robots.txt", base_url)

    print("built site/")
    print("  index +", len(data["providers"]), "provider pages + compare + privacy + about + contact + methodology + sitemap + robots + _redirects")
    print("  offers rendered into provider-page dynamic layer:", len(data["deals"]))
    print("  contact email:", contact_email)
    print("  sitemap urls:", len(all_paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())