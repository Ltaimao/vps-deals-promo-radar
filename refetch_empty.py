#!/usr/bin/env python3
"""Recheck empty, reachable providers with the declared bot and robots checks.

This replaces the former CDP fallback. It never uses a browser identity to
work around a denial. Primary snapshot timestamps prevent reuse of stale data.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from scraper import RobotsClient, extract_offers, offer_id_for

ROOT = Path(__file__).resolve().parent


def main(output=None):
    data = json.loads((ROOT / "data/offers.json").read_text())
    have = {d["provider_slug"] for d in data["deals"]}
    client, results = RobotsClient(), {}
    for provider in data["providers"]:
        if provider["slug"] in have:
            continue
        slug = provider["slug"]
        source = provider["source_url"] or provider["url"]
        if provider["fetch_status"] != "ok":
            results[slug] = {"status": "unreachable", "deals": [], "reason": "primary_fetch_failed"}
            continue
        code, body = client.fetch(source)
        deals = extract_offers(body.decode("utf-8", "replace"), source, provider["name"]) if code == 200 and body else []
        for deal in deals:
            deal["provider_slug"] = slug
            deal["offer_id"] = offer_id_for(slug, deal["offer_url"], deal["title"])
        results[slug] = {"status": "ok" if deals else "empty", "deals": deals,
                         "http_status": code, "reason": client.last_reason}
    out = {"generated_at": datetime.now(timezone.utc).isoformat(),
           "source_generated_at": data["generated_at"], "fetch_policy": "robots-v1", "results": results}
    target = Path(output) if output else ROOT / "data/refetch.json"
    target.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print("Rechecked", len(results), "empty providers; wrote", target)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    raise SystemExit(main(parser.parse_args().output))
