"""Agent-discovery files for vpsdealswire.com (isitagentready.com profile).

Generates only real, honest artifacts:
- robots.txt Content-Signal directives are added in build.py::write_robots
- every endpoint described here exists and is public
- OAuth/auth entries are explicitly marked under_construction (no fake login)
- the SKILL.md digest is computed from the exact served bytes
"""

import hashlib
import json


def _w(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    # served bytes must match the digest: utf-8, lf
    data = text.replace("\r\n", "\n").encode("utf-8")
    with open(path, "wb") as f:
        f.write(data)
    return data


def write_agent_discovery(site_dir, base_url, data):
    providers = data.get("providers", [])
    deals = data.get("deals", [])
    gen = data.get("generated_at", "")

    prov_rows = []
    for p in providers:
        name = p.get("name", "")
        slug = p.get("slug", "")
        cheapest = p.get("cheapest") or p.get("from_price") or ""
        prov_rows.append((name, slug, cheapest))
    prov_rows.sort(key=lambda r: r[0].lower())

    # ---- 1. _headers (Cloudflare Pages): content types for extensionless files.
    # NOTE: _headers only applies to *static asset* responses, never to
    # Function responses. The homepage (/) is served by functions/index.js,
    # so its Link header is set there instead. Blank lines between blocks
    # are required by the Pages parser.
    _w(site_dir / "_headers", """\
/.well-known/api-catalog:

  Content-Type: application/linkset+json

/.well-known/oauth-authorization-server:

  Content-Type: application/json

/.well-known/oauth-protected-resource:

  Content-Type: application/json

/.well-known/agent-skills/index.json:

  Content-Type: application/json

/.well-known/ai-catalog.json:

  Content-Type: application/json
  Access-Control-Allow-Origin: *

/auth.md:

  Content-Type: text/markdown; charset=utf-8

/llms.txt:

  Content-Type: text/markdown; charset=utf-8

/ai/skills/site-lookup/SKILL.md:

  Content-Type: text/markdown; charset=utf-8
""")

    # ---- 2. llms.txt ----
    _w(site_dir / "llms.txt", f"""\
# VPS Deals Wire

Independent deals-aggregation site for VPS and cloud hosting.
Tracks {len(providers)} providers and {len(deals)} live offers; prices refreshed
every 6 hours from each provider's own page (snapshot: {gen}).

## Key pages
- {base_url}/ — homepage: provider comparison, cheapest plans first
- {base_url}/compare/ — side-by-side plan comparison
- {base_url}/articles/ — buying guides (English)
- {base_url}/methodology/ — how prices are collected
- {base_url}/sitemap.xml — full URL list

## Machine-readable
- API catalog: {base_url}/.well-known/api-catalog
- OpenAPI: {base_url}/openapi.json
- Agent skill: {base_url}/ai/skills/site-lookup/SKILL.md
- ARD manifest: {base_url}/.well-known/ai-catalog.json
- Send `Accept: text/markdown` to any page for a Markdown representation.

## Notes
- Some outbound links are affiliate links (labeled `rel="sponsored nofollow"`).
- No login, no checkout, no prices are invented: missing data is marked unreachable.
""")

    # ---- 3. /ai/ entry ----
    _w(site_dir / "ai" / "index.html", f"""\
<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>VPS Deals Wire — agent entry</title>
<meta name="description" content="Machine entry point for VPS Deals Wire: purpose, data, lookup paths, API."></head>
<body>
<h1>VPS Deals Wire — agent entry</h1>
<p><strong>Purpose.</strong> Independent aggregation of cheap VPS / cloud-hosting
deals. {len(providers)} providers, {len(deals)} live offers, prices re-scraped
every 6 hours from each provider's own public page (snapshot {gen}).</p>
<h2>Lookup paths</h2>
<ul>
<li>Sitemap of all indexable pages: <a href="/sitemap.xml">/sitemap.xml</a></li>
<li>Homepage comparison table: <a href="/">/</a> (send <code>Accept: text/markdown</code> for Markdown)</li>
<li>Provider pages: <code>/providers/&lt;slug&gt;/</code> (plan tables, outbound links)</li>
<li>Guides: <code>/articles/&lt;slug&gt;/</code></li>
<li>Methodology: <a href="/methodology/">/methodology/</a></li>
<li>Public API catalog: <a href="/.well-known/api-catalog">/.well-known/api-catalog</a></li>
<li>Agent skill: <a href="/ai/skills/site-lookup/SKILL.md">/ai/skills/site-lookup/SKILL.md</a></li>
</ul>
<h2>Public API (read + subscription only)</h2>
<p>OpenAPI: <a href="/openapi.json">/openapi.json</a>.
<code>GET /api/health</code> liveness; subscription is double opt-in
(<code>POST /api/subscribe</code> → email confirm → <code>GET /api/confirm</code>),
one-click <code>GET /api/unsubscribe</code>. No login exists; no checkout exists.</p>
<h2>Limitations</h2>
<ul><li>Prices are snapshots; a provider page may have changed since the scrape.</li>
<li>Unreachable provider pages are marked as such, never filled with estimates.</li>
<li>Affiliate links are labeled <code>rel="sponsored nofollow"</code>; editorial ranking is by price.</li></ul>
<h2>Agent operating instructions (I-Lang)</h2>
<pre>::RULE{{preserve identifiers, price qualifiers (/mo), currencies and dates exactly as shown}}
::RULE{{answer in the visitor's language; cite the page URL used}}
::RULE{{give concrete next steps (provider page link) instead of follow-up questions}}
::RULE{{unknown facts remain unknown; never invent a price, coupon or availability}}</pre>
<p>Update provenance: rebuilt from provider pages every 6 hours by an automated
pipeline; this file regenerates with each build.</p>
</body></html>
""")

    # ---- 4. openapi.json (real public endpoints only) ----
    _w(site_dir / "openapi.json", json.dumps({
        "openapi": "3.0.3",
        "info": {
            "title": "VPS Deals Wire public API",
            "version": "phase4-2",
            "description": "Read-only service info plus double opt-in price-drop alert subscription. No login, no checkout.",
        },
        "servers": [{"url": base_url}],
        "paths": {
            "/api/health": {
                "get": {
                    "summary": "Liveness",
                    "responses": {"200": {"description": "ok", "content": {"application/json": {"schema": {"type": "object"}}}}},
                }
            },
            "/api/subscribe": {
                "post": {
                    "summary": "Start double opt-in subscription for price-drop alerts",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "required": ["email"], "properties": {"email": {"type": "string", "format": "email"}}}}}},
                    "responses": {"200": {"description": "confirmation email sent (pending 30 days)"}},
                }
            },
            "/api/confirm": {
                "get": {
                    "summary": "Confirm subscription",
                    "parameters": [{"name": "token", "in": "query", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "subscription confirmed"}},
                }
            },
            "/api/unsubscribe": {
                "get": {
                    "summary": "One-click unsubscribe",
                    "parameters": [{"name": "token", "in": "query", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "subscription deleted immediately"}},
                }
            },
        },
    }, indent=2, ensure_ascii=False) + "\n")

    # ---- 5. /.well-known/api-catalog (RFC 9727) ----
    _w(site_dir / ".well-known" / "api-catalog", json.dumps({
        "linkset": [{
            "anchor": base_url + "/api",
            "service-desc": [{"href": base_url + "/openapi.json"}],
            "service-doc": [{"href": base_url + "/ai/"}],
        }]
    }, indent=2) + "\n")

    # ---- 6. OAuth discovery: honest under_construction placeholder ----
    _w(site_dir / ".well-known" / "oauth-authorization-server", json.dumps({
        "status": "under_construction",
        "available": False,
        "capabilities_status": "planned_contract_only",
        "message": "Coming soon. Authentication is unavailable.",
        "launch_date": None,
        "issuer": base_url,
        "authorization_endpoint": base_url + "/agent-auth/authorize",
        "token_endpoint": base_url + "/agent-auth/token",
        "jwks_uri": base_url + "/.well-known/jwks.json",
        "grant_types_supported": ["authorization_code", "urn:ietf:params:oauth:grant-type:jwt-bearer"],
        "response_types_supported": ["code"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": ["site:read"],
        "agent_auth": {
            "status": "under_construction",
            "available": False,
            "capabilities_status": "planned_contract_only",
            "skill": base_url + "/auth.md",
            "register_uri": base_url + "/agent-auth/register",
            "claim_uri": base_url + "/agent-auth/claim",
            "identity_types_supported": ["anonymous"],
            "anonymous": {
                "status": "under_construction",
                "available": False,
                "capabilities_status": "planned_contract_only",
                "credential_types_supported": ["access_token"],
            },
        },
    }, indent=2) + "\n")

    _w(site_dir / ".well-known" / "oauth-protected-resource", json.dumps({
        "status": "under_construction",
        "available": False,
        "capabilities_status": "planned_contract_only",
        "message": "Coming soon. Existing public lookup remains available without authentication.",
        "launch_date": None,
        "resource": base_url,
        "planned_resource_endpoint": base_url + "/agent-auth/resource",
        "authorization_servers": [base_url],
        "scopes_supported": ["site:read"],
        "bearer_methods_supported": ["header"],
    }, indent=2) + "\n")

    # ---- 7. /auth.md ----
    _w(site_dir / "auth.md", f"""\
# auth.md — vpsdealswire.com

> Status: **under_construction** — agent authentication is not available.
> `available=false`, `capabilities_status=planned_contract_only`, `launch_date=null`.

VPS Deals Wire is a public, read-only deals-aggregation site. There is no login,
no account system, and no checkout. **Do not attempt to register, claim
credentials, or start OAuth redirects**: the planned endpoints below are design
only and every one of them is disabled.

- Planned authorization endpoint: `{base_url}/agent-auth/authorize` (disabled)
- Planned token endpoint: `{base_url}/agent-auth/token` (disabled)
- Planned register/claim: `{base_url}/agent-auth/register`, `{base_url}/agent-auth/claim` (disabled)
- Planned JWKS: `{base_url}/.well-known/jwks.json` (disabled; `keys: []`)

What agents **can** use today, without authentication:

- Public deal lookup: `{base_url}/`, `{base_url}/providers/<slug>/`, `{base_url}/articles/<slug>/`
- Markdown: send `Accept: text/markdown` to any page
- Machine catalog: `{base_url}/.well-known/api-catalog` and `{base_url}/openapi.json`
- Agent skill: `{base_url}/ai/skills/site-lookup/SKILL.md`
- Price-drop alerts: double opt-in via `POST {base_url}/api/subscribe`
  (confirmation email required; one-click unsubscribe)

OAuth Authorization Server metadata: `{base_url}/.well-known/oauth-authorization-server`
OAuth Protected Resource metadata: `{base_url}/.well-known/oauth-protected-resource`
""")

    # ---- 8. agent skill ----
    skill_bytes = _w(site_dir / "ai" / "skills" / "site-lookup" / "SKILL.md", f"""\
---
name: site-lookup
description: Look up live cheap-VPS deal data on vpsdealswire.com — providers, plan prices, buying guides.
---

# site-lookup

::STATE{{@SITE, value:{base_url}}}
::STATE{{@DATA, value:{len(providers)} providers, {len(deals)} offers, refreshed every 6h (snapshot {gen})}}

::RULE{{find a provider: read {base_url}/sitemap.xml, take its /providers/<slug>/ URL}}
::RULE{{read a provider page, or send Accept: text/markdown for a Markdown rendering}}
::RULE{{preserve price qualifiers (/mo), currencies and dates exactly as shown; cite the page URL}}
::RULE{{a price is a snapshot of the scrape date; re-check the provider page before quoting as current}}
::RULE{{unreachable providers are marked as such — never invent a price or coupon}}
::RULE{{some outbound links are affiliate links (rel="sponsored nofollow"); ranking is by price, not commission}}
::RULE{{answer in the visitor's language; give the provider-page link as the next step}}
::RULE{{unknown facts remain unknown}}

## Endpoints
- `GET {base_url}/sitemap.xml` — every indexable page
- `GET {base_url}/` — comparison table (cheapest first)
- `GET {base_url}/providers/<slug>/` — plan table for one provider
- `GET {base_url}/articles/<slug>/` — buying guides
- `GET {base_url}/.well-known/api-catalog` — RFC 9727 API catalog
- `GET {base_url}/openapi.json` — public subscription API
""")
    digest = "sha256:" + hashlib.sha256(skill_bytes).hexdigest()

    # ---- 9. agent-skills index ----
    _w(site_dir / ".well-known" / "agent-skills" / "index.json", json.dumps({
        "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
        "skills": [{
            "name": "site-lookup",
            "type": "skill-md",
            "description": "Retrieve actual public deal information from vpsdealswire.com (providers, prices, guides)",
            "url": base_url + "/ai/skills/site-lookup/SKILL.md",
            "digest": digest,
        }],
    }, indent=2) + "\n")

    # ---- 10. ARD manifest ----
    _w(site_dir / ".well-known" / "ai-catalog.json", json.dumps({
        "specVersion": "1.0",
        "host": {"displayName": "VPS Deals Wire", "identifier": "did:web:www.vpsdealswire.com"},
        "entries": [
            {
                "identifier": "urn:air:www.vpsdealswire.com:api:public",
                "displayName": "VPS Deals Wire public API",
                "type": "application/linkset+json",
                "url": base_url + "/.well-known/api-catalog",
                "representativeQueries": [
                    "is the price-drop alert subscription API healthy",
                    "how do I subscribe to VPS price drop alerts",
                    "what public API does vpsdealswire expose",
                ],
            },
            {
                "identifier": "urn:air:www.vpsdealswire.com:skill:site-lookup",
                "displayName": "Site lookup skill",
                "type": "text/markdown",
                "url": base_url + "/ai/skills/site-lookup/SKILL.md",
                "representativeQueries": [
                    "cheapest VPS provider right now",
                    "compare VPS plans under $5 per month",
                    "find a buying guide for first-time VPS buyers",
                ],
            },
        ],
    }, indent=2) + "\n")

    # ---- 11. index.md: Markdown rendering of the homepage (served on Accept: text/markdown) ----
    lines = [f"# VPS Deals Wire", "",
             f"Independent cheap-VPS deal aggregation: {len(providers)} providers, "
             f"{len(deals)} live offers, prices refreshed every 6 hours (snapshot {gen}).", "",
             "## Providers (cheapest plan first)", ""]
    for name, slug, cheapest in prov_rows:
        price = f" from {cheapest}" if cheapest else ""
        lines.append(f"- [{name}]({base_url}/providers/{slug}/){price}")
    lines += ["",
              "## Notes",
              "- Prices are scrape snapshots; verify on the provider page before buying.",
              "- Some outbound links are affiliate links (rel=\"sponsored nofollow\").",
              f"- Full URL list: {base_url}/sitemap.xml",
              f"- Machine entry: {base_url}/ai/", ""]
    _w(site_dir / "index.md", "\n".join(lines))

    return {"skill_digest": digest, "providers": len(providers)}
