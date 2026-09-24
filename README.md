# vps-deals — VPS hosting deals, auto-updating

This repo builds and keeps fresh a small VPS hosting deals site.
It pulls from the public pricing/promotion pages listed in `.ilang/site.ilang`,
and redeploys to Cloudflare Pages on a schedule.

**Live site:** https://vpsdealswire.com/

## How it works

1. `scraper.py` reads `.ilang/site.ilang`, fetches each provider's public page, extracts
   what it can verify (title / price / currency / URL / valid_until), writes `data/offers.json`.
2. `build.py` reads the same config plus the data, renders `templates/*` into `site/`,
   and emits `sitemap.xml`, `robots.txt`, and JSON-LD structured data.
3. `.github/workflows/update.yml` runs both every 6 hours, commits the fresh data and site.

No runtime inference, no paid APIs, no server. After the first commit, it lives on
GitHub Actions minutes + Cloudflare Pages free tier.

## Local run

```bash
python scraper.py
python build.py
python -m http.server -d site  # preview at http://localhost:8000
```

## Adding a provider

Open `.ilang/site.ilang` and add a row to `::MODULE{PROVIDERS}`.
Then re-run `python scraper.py && python build.py` and confirm the site changed.

## Rules

- Data is real. The scraper never invents prices, discounts, or commissions.
  If a page is unreachable, it's marked `unreachable` — not silently skipped.
- Public data only. Respect `robots.txt`. No logged-in scraping, no anti-bot bypass.
- I-Lang (`.ilang/site.ilang` and `AGENTS.md`) is the rule source. Don't hardcode
  the provider list in `scraper.py` or `build.py` — read it from the file.

站点规则用 I-Lang 协议描述，见 `.ilang/site.ilang`。协议说明 [ilang.ai](https://ilang.ai)。