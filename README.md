# VPS Deals Wire — VPS hosting deals, auto-updating

This repo builds and keeps fresh a small VPS hosting deals site.
It pulls from the public pricing/promotion pages listed in `.ilang/site.ilang`,
and redeploys to Cloudflare Pages on a schedule.

**Live site:** https://www.vpsdealswire.com/

## How it works

1. `scraper.py` checks robots.txt for its declared bot identity, including redirect targets, then reads `.ilang/site.ilang`, fetches each provider's public page, extracts
   what it can verify (title / price / currency / URL / valid_until), writes `data/offers.json`.
2. `build.py` reads the same config plus the data, renders `templates/*` into `site/`,
   and emits `sitemap.xml`, `robots.txt`, and JSON-LD structured data.
3. `.github/workflows/update.yml` runs both every 6 hours, commits fresh data and deploys the generated site.

The static build uses no runtime inference or paid API. Production subscriptions use an independent Cloudflare Worker, KV, and Resend; deploying Pages does not deploy or test that service.

## Local run

```bash
# Build the committed snapshot without modifying tracked history.
python build.py --preserve-history
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
## Current operations and growth plan

- [Current environment, verification commands, deployment, and unverified handover claims](docs/OPERATIONS.md)
- [90-day SEO, marketing, and affiliate revenue plan](docs/GROWTH_PLAN.md)

Use `python3 -m unittest discover -s tests -v` for offline regression tests.
Local builds can preserve tracked history with `python3 build.py --preserve-history`.
To build a fresh validation snapshot separately: `python3 build.py --data /tmp/vps-offers-check.json --output /tmp/vps-fresh-site --preserve-history`.
Default builds keep using committed data; validation scraping does not overwrite production data.
Amounts without an explicit billing period are not advertised as monthly VPS prices.
Currency is never converted with a hardcoded exchange rate.

## Daily editorial publishing

A reviewed queue publishes one article each day at a scheduled 08:00 Asia/Shanghai trigger (00:00 UTC), subject to GitHub runner/deployment delay. The first 14 complete guides cover October 24–November 6, 2026. See [the calendar and operating instructions](docs/DAILY_EDITORIAL.md). No runtime AI service or new credential is required. An empty or invalid queue fails visibly instead of publishing filler. Validate with `python3 editorial.py validate`.
