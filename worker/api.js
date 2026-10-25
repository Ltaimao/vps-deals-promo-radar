import { DurableObject } from "cloudflare:workers";

/**
 * vpsdealswire-api — subscription + price-drop alerts for vpsdealswire.com
 *
 * Endpoints:
 *   POST /api/subscribe        {email} -> pending + confirmation email (double opt-in)
 *   GET  /api/confirm?token=   -> activate subscription (HTML page)
 *   GET  /api/unsubscribe?token= -> delete everything (HTML page)
 *   GET  /api/health          -> {ok:true}
 * Scheduled (every 6h): fetch offers.json + history.json from the public repo,
 *   detect NEW LOWEST prices per deal, email active subscribers.
 *
 * Rules (from .ilang/site.ilang):
 *   - double opt-in: pending until the confirmation link is clicked. Never
 *     send alerts to unconfirmed addresses.
 *   - every email carries a one-click unsubscribe link; unsubscribing deletes
 *     all records immediately.
 *   - price-drop alerts fire only on a NEW ALL-TIME LOW per deal (debounces
 *     scraper extraction noise, e.g. UpCloud's strict $6<->$7 oscillation).
 *   - sending is transactional only (confirmations + alerts the user asked
 *     for). No newsletters, no marketing.
 */

const SITE = "https://www.vpsdealswire.com";
const FROM = { email: "alerts@vpsdealswire.com", name: "VPS Deals Wire" };
const OFFERS_URL =
  "https://raw.githubusercontent.com/Ltaimao/vps-deals-promo-radar/main/data/offers.json";
const HISTORY_URL =
  "https://raw.githubusercontent.com/Ltaimao/vps-deals-promo-radar/main/data/history.json";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const SUB_TTL = 60 * 60 * 24 * 30; // pending tokens live 30 days

async function sha256(s) {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function normEmail(raw) {
  return (raw || "").trim().toLowerCase();
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json",
      "access-control-allow-origin": "https://www.vpsdealswire.com",
      "access-control-allow-methods": "POST, GET, OPTIONS",
      "access-control-allow-headers": "content-type",
    },
  });
}

function page(title, body) {
  return new Response(
    "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">" +
      "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">" +
      "<title>" + title + " — VPS Deals Wire</title>" +
      "<style>body{font-family:system-ui,sans-serif;max-width:560px;margin:8vh auto;" +
      "padding:0 20px;color:#1a2333;line-height:1.6}h1{font-size:1.4rem}" +
      "a{color:#1677ff}.card{background:#f5f8ff;border:1px solid #dbe7ff;" +
      "border-radius:12px;padding:20px 24px}</style></head><body>" +
      "<div class=\"card\"><h1>" + title + "</h1>" + body + "</div>" +
      "<p><a href=\"" + SITE + "/\">← back to VPS Deals Wire</a></p>" +
      "</body></html>",
    { status: 200, headers: { "content-type": "text/html; charset=utf-8" } }
  );
}

async function sendMail(env, to, subject, text, html) {
  // Resend (free tier: 100/day, 3000/month) — key lives in the Worker secret
  // RESEND_API_KEY, never in code or chat. Requires the sending domain
  // (vpsdealswire.com) verified in the Resend dashboard.
  if (!env.RESEND_API_KEY) throw new Error("missing RESEND_API_KEY");
  const r = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: "Bearer " + env.RESEND_API_KEY,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: FROM.name + " <" + FROM.email + ">",
      to: [to],
      reply_to: "contact@vpsdealswire.com",
      subject,
      text,
      html,
    }),
  });
  if (!r.ok) throw new Error("resend " + r.status);
}

function confirmEmailBody(link) {
  const text =
    "You asked VPS Deals Wire to send you price-drop alerts.\n\n" +
    "Click this link to confirm (double opt-in):\n" + link + "\n\n" +
    "The link expires in 30 days. If you didn't ask for this, just ignore it — " +
    "nothing will be sent.\n\n" +
    "Every alert email carries a one-click unsubscribe link.";
  const html =
    "<p>You asked <strong>VPS Deals Wire</strong> to send you price-drop alerts.</p>" +
    "<p><a href=\"" + link + "\">Click here to confirm your subscription</a></p>" +
    "<p>The link expires in 30 days. If you didn't ask for this, just ignore it — " +
    "nothing will be sent.</p>" +
    "<p>Every alert email carries a one-click unsubscribe link.</p>";
  return { text, html };
}

async function handleSubscribe(request, env) {
  const ctype = request.headers.get("content-type") || "";
  // No-JS fallback: a plain HTML form posts urlencoded; answer with a page.
  const isForm = ctype.includes("application/x-www-form-urlencoded");
  const fail = (error, status, title, bodyHtml) =>
    isForm ? page(title, bodyHtml) : json({ ok: false, error }, status);
  const done = (title, bodyHtml) =>
    isForm ? page(title, bodyHtml) : json({ ok: true });

  let body;
  try {
    if (isForm) {
      const fd = await request.formData();
      body = { email: fd.get("email") };
    } else {
      body = await request.json();
    }
  } catch {
    return fail("invalid_json", 400, "Bad request",
      "<p>The subscription request was malformed. Please go back and try again.</p>");
  }
  const email = normEmail(body.email);
  if (!EMAIL_RE.test(email) || email.length > 254) {
    return fail("invalid_email", 400, "Invalid email",
      "<p>That email address doesn't look valid. Please go back and try again.</p>");
  }
  // basic per-IP rate limit: 5 subscribes/hour
  const ip =
    request.headers.get("cf-connecting-ip") ||
    request.headers.get("x-forwarded-for") ||
    "unknown";
  const rlKey = "rl:" + (await sha256(ip)).slice(0, 16);
  const rl = parseInt((await env.SUBS.get(rlKey)) || "0", 10);
  if (rl >= 5)
    return fail("rate_limited", 429, "Too many attempts",
      "<p>Too many subscription attempts — please try again later.</p>");
  await env.SUBS.put(rlKey, String(rl + 1), { expirationTtl: 3600 });

  const ehash = await sha256("vpsdw:" + email);
  const existing = await env.SUBS.get("sub:" + ehash, "json");
  // Never reveal whether an address is subscribed (anti-enumeration).
  // If already active, stay silent; if pending, resend the confirmation.
  let token;
  if (existing && existing.status === "active") {
    return done("Check your inbox",
      "<p>This address is already subscribed. If you didn't get a confirmation " +
      "before, check your spam folder.</p>");
  }
  token = existing && existing.status === "pending" && existing.token
    ? existing.token : crypto.randomUUID();
  // Keep both pending records on the same TTL, including resends of legacy records.
  await env.SUBS.put(
    "sub:" + ehash,
    JSON.stringify({
      status: "pending", email, token,
      created_at: existing && existing.created_at || new Date().toISOString(),
      requested_at: new Date().toISOString(),
    }),
    { expirationTtl: SUB_TTL }
  );
  await env.SUBS.put(
    "pending:" + token,
    JSON.stringify({ ehash, email, created_at: new Date().toISOString() }),
    { expirationTtl: SUB_TTL }
  );

  const link = SITE + "/api/confirm?token=" + token;
  const { text, html } = confirmEmailBody(link);
  try {
    await sendMail(env, email, "Confirm your VPS price-drop alerts", text, html);
  } catch (e) {
    // Don't leak provider errors; the pending record lets them retry.
    return fail("send_failed", 502, "Something went wrong",
      "<p>The confirmation email couldn't be sent. Please try again in a few minutes.</p>");
  }
  return done("Check your inbox",
    "<p>We sent a confirmation email to <strong>" + escapeHtml(email) + "</strong>. " +
    "Click the link in it within 30 days — until then, nothing else will be sent.</p>");
}

async function handleConfirm(url, env) {
  const token = url.searchParams.get("token") || "";
  if (!/^[0-9a-f-]{36}$/.test(token)) {
    return page("Invalid link", "<p>This confirmation link is invalid.</p>");
  }
  const rec = await env.SUBS.get("pending:" + token, "json");
  if (!rec) {
    return page(
      "Link expired",
      "<p>This confirmation link has expired or was already used. " +
        "Please subscribe again on the site.</p>"
    );
  }
  const unsub = crypto.randomUUID();
  await env.SUBS.put(
    "sub:" + rec.ehash,
    JSON.stringify({
      status: "active",
      email: rec.email,
      confirmed_at: new Date().toISOString(),
      unsub_token: unsub,
    })
  );
  await env.SUBS.put("unsub:" + unsub, rec.ehash);
  await env.SUBS.delete("pending:" + token);
  return page(
    "You're in",
    "<p><strong>" + escapeHtml(rec.email) + "</strong> is now subscribed to " +
      "VPS price-drop alerts. You'll get an email when a tracked deal hits a " +
      "new lowest price.</p>" +
      "<p>Every email has a one-click unsubscribe link. " +
      "<a href=\"" + SITE + "/api/unsubscribe?token=" + unsub + "\">Unsubscribe now</a> " +
      "if you change your mind.</p>"
  );
}

async function handleUnsubscribe(url, env) {
  const token = url.searchParams.get("token") || "";
  if (!/^[0-9a-f-]{36}$/.test(token)) {
    return page("Invalid link", "<p>This unsubscribe link is invalid.</p>");
  }
  const ehash = await env.SUBS.get("unsub:" + token);
  if (ehash) {
    const sub = await env.SUBS.get("sub:" + ehash, "json");
    await env.SUBS.delete("sub:" + ehash);
    await env.SUBS.delete("unsub:" + token);
    if (sub && sub.token) await env.SUBS.delete("pending:" + sub.token);
    // drop this subscriber's per-deal alert markers as well
    let acursor;
    do {
      const alist = await env.SUBS.list({ prefix: "alerted:", cursor: acursor });
      for (const k of alist.keys) {
        if (k.name.endsWith(":sub:" + ehash)) await env.SUBS.delete(k.name);
      }
      acursor = alist.list_complete ? undefined : alist.cursor;
    } while (acursor);
  }
  // Always show the same page (anti-enumeration).
  return page(
    "Unsubscribed",
    "<p>Done — this address will receive no further emails from VPS Deals Wire. " +
      "All records for it have been deleted.</p>"
  );
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

// ---------- price-drop alerts (scheduled) ----------

async function handleScheduled(env) {
  const [offersRes, histRes] = await Promise.all([
    fetch(OFFERS_URL, { cf: { cacheTtl: 300 } }),
    fetch(HISTORY_URL, { cf: { cacheTtl: 300 } }),
  ]);
  if (!offersRes.ok || !histRes.ok) return;
  const offers = await offersRes.json();
  const history = await histRes.json();
  const series = history.deal_series || {};
  const now = new Date().toISOString();

  // Two-snapshot confirmation (I-Lang RULE): a new all-time low becomes
  // alertable only after a second consecutive snapshot shows the same price.
  // First sighting -> dropwatch:<key> = {price, prev}; the price moving away
  // voids the watch; only a repeated sighting promotes it to "confirmed".
  const confirmed = [];
  let watching = 0;
  for (const d of offers.deals || []) {
    if (d.price == null || d.billing_period !== "month") continue;
    if (d.valid_until && Date.parse(d.valid_until) < Date.now()) continue;
    const key =
      d.offer_id ||
      (await sha256(
        "vpsdw:" +
          [d.provider_slug, d.offer_url, d.title]
            .map((p) => (p || "").trim().toLowerCase().replace(/\s+/g, " "))
            .join("\x00")
      )).slice(0, 16);
    const s = series[key];
    // Legacy points have unknown units. Only compare explicit monthly history
    // in the same currency; never infer a monthly baseline from old amounts.
    const points = s && s.monthly_points_by_currency && s.monthly_points_by_currency[d.currency];
    if (!points || points.length < 2) continue;
    const prices = points.map((p) => p[1]);
    const prevLow = Math.min(...prices.slice(0, -1));
    const cur = prices[prices.length - 1];
    if (Number(d.price) !== cur) continue;
    const watch = await env.SUBS.get("dropwatch:" + key, "json");
    if (watch && watch.price === cur && watch.snapshot && watch.snapshot !== offers.generated_at) {
      // confirmed: the new low survived a full snapshot cycle
      confirmed.push({
        key,
        provider: d.provider_name,
        slug: d.provider_slug,
        title: d.title,
        cur,
        prev: watch.prev,
        currency: d.currency || "USD",
      });
    } else if (cur < prevLow) {
      // first sighting of a new (or deeper) low: watch it, do not alert yet
      await env.SUBS.put(
        "dropwatch:" + key,
        JSON.stringify({ price: cur, prev: prevLow, snapshot: offers.generated_at })
      );
      watching++;
    } else if (watch && watch.price !== cur) {
      // price moved away from the watched low: void the watch
      await env.SUBS.delete("dropwatch:" + key);
    }
  }

  // collect active subscribers (KV list, paginated)
  const subs = [];
  let expiredPending = 0;
  let cursor;
  do {
    const list = await env.SUBS.list({ prefix: "sub:", cursor });
    for (const k of list.keys) {
      const sub = await env.SUBS.get(k.name, "json");
      if (sub && sub.status === "pending") {
        // Old releases did not put a TTL on sub:<hash>. Remove only provably
        // expired pending records; active or undated records are never guessed.
        const created = Date.parse(sub.requested_at || sub.created_at);
        if (Number.isFinite(created) && Date.now() - created > SUB_TTL * 1000) {
          await env.SUBS.delete(k.name);
          if (sub.token) await env.SUBS.delete("pending:" + sub.token);
          expiredPending++;
        }
        continue;
      }
      if (sub && sub.status === "active" && EMAIL_RE.test(sub.email))
        subs.push({ kv: k.name, ...sub });
    }
    cursor = list.list_complete ? undefined : list.cursor;
  } while (cursor);

  // Per-subscriber alert state: mark alerted only after a SUCCESSFUL send,
  // so a failed send is retried on the next run instead of being lost.
  const sym = { USD: "$", EUR: "€", GBP: "£" };
  let sent = 0;
  let failed = 0;
  for (const sub of subs) {
    const mine = [];
    for (const x of confirmed) {
      const akey = "alerted:" + x.key + ":" + sub.kv;
      const already = parseFloat((await env.SUBS.get(akey)) || "Infinity");
      if (x.cur < already) mine.push({ ...x, akey });
    }
    if (!mine.length) continue;
    const unsubLink = SITE + "/api/unsubscribe?token=" + sub.unsub_token;
    const lines = mine.map(
      (x) =>
        "- " + x.provider + " — " + x.title + ": now " +
        (sym[x.currency] || x.currency + " ") + x.cur + "/mo (was " +
        (sym[x.currency] || x.currency + " ") + x.prev + ")"
    );
    const text =
      "Price drops on VPS Deals Wire:\n\n" + lines.join("\n") + "\n\n" +
      mine.map((x) => x.provider + ": " + SITE + "/providers/" + x.slug + "/").join("\n") +
      "\n\nUnsubscribe any time (one click, immediate):\n" + unsubLink;
    const html =
      "<p><strong>Price drops on VPS Deals Wire:</strong></p><ul>" +
      mine.map(
        (x) =>
          "<li>" + escapeHtml(x.provider) + " — " + escapeHtml(x.title) + ": now <strong>" +
          escapeHtml((sym[x.currency] || x.currency + " ") + x.cur) + "/mo</strong> (was " +
          escapeHtml((sym[x.currency] || x.currency + " ") + x.prev) + ") " +
          "<a href=\"" + SITE + "/providers/" + x.slug + "/\">view</a></li>"
      ).join("") + "</ul>" +
      "<p><a href=\"" + unsubLink + "\">Unsubscribe</a> — one click, immediate.</p>";
    const subject =
      mine.length === 1
        ? "Price drop: " + mine[0].provider + " now " +
          (sym[mine[0].currency] || "") + mine[0].cur + "/mo"
        : mine.length + " VPS price drops";
    try {
      await sendMail(env, sub.email, subject, text, html);
      for (const x of mine) await env.SUBS.put(x.akey, String(x.cur));
      sent++;
    } catch {
      // per-recipient failure must not block the rest; unmarked -> retried next run
      failed++;
    }
  }
  await env.SUBS.put(
    "meta:last_cron",
    now + " confirmed=" + confirmed.length + " watching=" + watching +
      " sent=" + sent + " failed=" + failed + " expired_pending=" + expiredPending
  );
}

/* ------------------------------------------------------------------
 * MCP server (Model Context Protocol, Streamable HTTP) — read-only.
 * Serves the same public deal dataset the static site renders
 * (GET https://www.vpsdealswire.com/api/deals.json, rebuilt every 6h).
 * No login, no writes, no invented data.
 * ------------------------------------------------------------------ */
const MCP_NAME = "vpsdealswire-mcp";
const MCP_VERSION = "1.0.0";
const MCP_DATASET_URL = SITE + "/data/deals.json";
let mcpCache = null; // {at, data}

function mcpJson(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json",
      "access-control-allow-origin": "*",
      "access-control-allow-methods": "POST, GET, OPTIONS",
      "access-control-allow-headers": "content-type, accept",
    },
  });
}

function mcpOk(id, result) {
  return mcpJson({ jsonrpc: "2.0", id: id === undefined ? null : id, result });
}

function mcpErr(id, code, message) {
  return mcpJson({ jsonrpc: "2.0", id: id === undefined ? null : id,
                   error: { code, message } });
}

async function mcpDataset() {
  const now = Date.now();
  if (mcpCache && now - mcpCache.at < 3600 * 1000) return mcpCache.data;
  const res = await fetch(MCP_DATASET_URL, { cf: { cacheTtl: 3600 } });
  if (!res.ok) throw new Error("dataset unavailable (HTTP " + res.status + ")");
  const data = await res.json();
  mcpCache = { at: now, data };
  return data;
}

const MCP_TOOLS = [
  {
    name: "list_providers",
    description:
      "List all VPS providers tracked by VPS Deals Wire with cheapest observed price.",
    inputSchema: { type: "object", properties: {},
                   additionalProperties: false },
  },
  {
    name: "get_provider",
    description: "Get details and current offers for one provider by slug.",
    inputSchema: {
      type: "object",
      properties: {
        slug: { type: "string", description: "Provider slug, e.g. digitalocean" },
      },
      required: ["slug"],
      additionalProperties: false,
    },
  },
  {
    name: "find_deals",
    description:
      "Find VPS offers at or below a maximum monthly USD price, optionally limited to one provider.",
    inputSchema: {
      type: "object",
      properties: {
        max_usd: { type: "number", description: "Maximum monthly price in USD" },
        provider_slug: { type: "string", description: "Provider slug filter" },
        limit: { type: "number", description: "Max offers to return (default 20, max 50)" },
      },
      additionalProperties: false,
    },
  },
];

async function mcpCallTool(name, args) {
  const ds = await mcpDataset();
  const providers = ds.providers || [];
  const offers = ds.offers || [];
  if (name === "list_providers") {
    return providers.map((p) => ({
      name: p.name, slug: p.slug, page: p.page,
      cheapest_usd: p.cheapest_usd, plans: p.plans,
    }));
  }
  if (name === "get_provider") {
    const slug = (args && args.slug) || "";
    const p = providers.find((x) => x.slug === slug);
    if (!p) throw new Error("unknown provider slug: " + slug);
    return Object.assign({}, p, {
      offers: offers.filter((o) => o.provider_slug === slug).slice(0, 50),
    });
  }
  if (name === "find_deals") {
    let list = offers.slice();
    if (args && args.provider_slug) {
      list = list.filter((o) => o.provider_slug === args.provider_slug);
    }
    if (args && typeof args.max_usd === "number") {
      list = list.filter((o) => typeof o.price_usd === "number" &&
                                o.price_usd <= args.max_usd);
    }
    list.sort((a, b) => (a.price_usd === null ? 1e9 : a.price_usd) -
                        (b.price_usd === null ? 1e9 : b.price_usd));
    const limit = Math.min((args && args.limit) || 20, 50);
    return list.slice(0, limit);
  }
  throw new Error("unknown tool: " + name);
}

async function handleMcp(request) {
  if (request.method === "GET") {
    return mcpJson({ name: MCP_NAME, version: MCP_VERSION,
                     transport: "streamable-http",
                     note: "POST JSON-RPC 2.0 here (initialize, tools/list, tools/call)." });
  }
  if (request.method !== "POST") {
    return mcpJson({ error: "method not allowed" }, 405);
  }
  let body;
  try {
    body = await request.json();
  } catch (e) {
    return mcpErr(null, -32700, "parse error");
  }
  const id = body && body.id !== undefined ? body.id : null;
  if (!body || body.jsonrpc !== "2.0" || typeof body.method !== "string") {
    return mcpErr(id, -32600, "invalid request");
  }
  try {
    if (body.method === "initialize") {
      return mcpOk(id, {
        protocolVersion: "2025-03-26",
        capabilities: { tools: {} },
        serverInfo: { name: MCP_NAME, version: MCP_VERSION },
      });
    }
    if (body.method === "tools/list") {
      return mcpOk(id, { tools: MCP_TOOLS });
    }
    if (body.method === "tools/call") {
      const params = body.params || {};
      const result = await mcpCallTool(params.name, params.arguments || {});
      return mcpOk(id, {
        content: [{ type: "text", text: JSON.stringify(result) }],
      });
    }
    if (body.method.indexOf("notifications/") === 0) {
      return new Response(null, { status: 202 });
    }
    return mcpErr(id, -32601, "method not found: " + body.method);
  } catch (e) {
    return mcpErr(id, -32602, String((e && e.message) || e));
  }
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return json({ ok: true });
    if (url.pathname === "/mcp") return handleMcp(request);
    if (url.pathname === "/api/subscribe" && request.method === "POST") {
      return handleSubscribe(request, env);
    }
    if (url.pathname === "/api/confirm" && request.method === "GET") {
      return handleConfirm(url, env);
    }
    if (url.pathname === "/api/unsubscribe" && request.method === "GET") {
      return handleUnsubscribe(url, env);
    }
    if (url.pathname === "/api/health") {
      return json({ ok: true, version: "phase4-2" });
    }
    if (url.pathname.startsWith("/api/youtube/jobs/")) {
      return handleYouTubeJob(request, env);
    }
    if (url.pathname === "/api/youtube/publish" && request.method === "POST") {
      return handleYouTubePublish(request, env);
    }
    if (url.pathname === "/api/youtube/delete" && request.method === "POST") {
      return handleYouTubeDelete(request, env);
    }
    if (url.pathname === "/api/gsc/query" && request.method === "GET") {
      return handleGscQuery(request, env);
    }
    if (url.pathname === "/api/gsc/sites" && request.method === "GET") {
      return handleGscSites(request, env);
    }
    if (url.pathname === "/api/x/post" && request.method === "POST") {
      return handleXPost(request, env);
    }
    if (url.pathname === "/api/x/me" && request.method === "GET") {
      return handleXMe(request, env);
    }
    if (url.pathname === "/api/deals-snapshot" && request.method === "GET") {
      return handleDealsSnapshot();
    }
    if (url.pathname === "/api/ga4/query" && request.method === "GET") {
      return handleGa4Query(request, env);
    }
    return json({ ok: false, error: "not_found" }, 404);
  },
  async scheduled(event, env, ctx) {
    ctx.waitUntil(handleScheduled(env));
  },
};

// ---------- GA4 Data API ----------
const GA4_PROPERTY_ID = "556451114"; // VPS Deals Wire

async function ga4AccessToken(env) {
  const cid = env.GSC_CLIENT_ID, csec = env.GSC_CLIENT_SECRET, rt = env.GA4_REFRESH_TOKEN;
  if (!cid || !csec || !rt) throw new Error("ga4_not_configured");
  const r = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      client_id: cid,
      client_secret: csec,
      refresh_token: rt,
    }),
  });
  if (!r.ok) throw new Error("ga4_token_refresh_failed:" + r.status);
  const j = await r.json();
  if (!j.access_token) throw new Error("ga4_token_no_access_token");
  return j.access_token;
}

async function handleGa4Query(request, env) {
  if (!ytApiAuth(request, env)) return json({ ok: false, error: "unauthorized" }, 401);
  const q = new URL(request.url).searchParams;
  const days = Math.min(Math.max(parseInt(q.get("days") || "28", 10) || 28, 1), 90);
  const dim = (q.get("dimension") || "date").toLowerCase();
  const dimension = ["date", "page", "country"].includes(dim) ? dim : "date";
  const end = new Date();
  end.setDate(end.getDate() - 1); // GA4 data lags ~1 day
  const start = new Date(end);
  start.setDate(start.getDate() - (days - 1));
  const fmt = (d) => d.toISOString().slice(0, 10);

  let access;
  try {
    access = await ga4AccessToken(env);
  } catch (e) {
    return json({ ok: false, error: String((e && e.message) || e) }, 502);
  }

  const dimMap = { date: "date", page: "pagePath", country: "country" };
  const body = {
    property: "properties/" + GA4_PROPERTY_ID,
    dateRanges: [{ startDate: fmt(start), endDate: fmt(end) }],
    dimensions: [{ name: dimMap[dimension] }],
    metrics: [{ name: "activeUsers" }, { name: "sessions" }, { name: "screenPageViews" }],
    orderBys: [{ metric: { metricName: "screenPageViews" }, desc: true }],
    limit: 1000,
  };
  const r = await fetch("https://analyticsdata.googleapis.com/v1beta/properties/" + GA4_PROPERTY_ID + ":runReport", {
    method: "POST",
    headers: { Authorization: "Bearer " + access, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const t = await r.text();
    return json({ ok: false, error: "ga4_api_error:" + r.status, detail: t.slice(0, 300) }, 502);
  }
  const j = await r.json();
  const rows = j.rows || [];
  let users = 0, sessions = 0, views = 0;
  const top_rows = rows.slice(0, 20).map((row) => {
    const vals = row.metricValues || [];
    const u = parseInt(vals[0]?.value || "0", 10);
    const s = parseInt(vals[1]?.value || "0", 10);
    const v = parseInt(vals[2]?.value || "0", 10);
    users += u; sessions += s; views += v;
    return { key: row.dimensionValues?.[0]?.value || "", users: u, sessions: s, views: v };
  });
  // totals need full sum, not just top 20
  for (const row of rows.slice(20)) {
    const vals = row.metricValues || [];
    users += parseInt(vals[0]?.value || "0", 10);
    sessions += parseInt(vals[1]?.value || "0", 10);
    views += parseInt(vals[2]?.value || "0", 10);
  }
  return json({
    ok: true, property: GA4_PROPERTY_ID,
    startDate: fmt(start), endDate: fmt(end), dimension,
    total_users: users, total_sessions: sessions, total_views: views,
    top_rows,
  });
}

// ---------- Deals snapshot (for Chrome extension) ----------
// Public, read-only. Returns a compact list of cheapest deals per provider.
// Data is fetched from the public GitHub repo (same source as the site).
// CORS is open for chrome-extension:// origins; the extension also caches for 6h.
async function handleDealsSnapshot() {
  try {
    const res = await fetch(OFFERS_URL, { cf: { cacheTtl: 3600 } });
    if (!res.ok) return json({ ok: false, error: "upstream_failed" }, 502);
    const data = await res.json();
    const deals = (data.deals || [])
      .filter((d) => typeof d.price === "number")
      .map((d) => ({
        provider_name: d.provider_name,
        provider_slug: d.provider_slug,
        title: d.title,
        price: d.price,
        currency: d.currency || "USD",
        offer_url: d.offer_url,
      }));
    return new Response(
      JSON.stringify({ ok: true, generated_at: data.generated_at, deals }),
      {
        headers: {
          "content-type": "application/json",
          "access-control-allow-origin": "*",
          "access-control-allow-methods": "GET, OPTIONS",
          "cache-control": "public, max-age=3600",
        },
      }
    );
  } catch (e) {
    return json({ ok: false, error: "failed" }, 500);
  }
}

// ---------- YouTube publish (server-side, no browser session) ----------
// The daily cron renders the mp4, commits it to static/videos/<slug>.mp4,
// pushes, waits for Pages to serve it, then POSTs here. The Worker fetches
// the video from the public site URL and uploads it to the @VPSDealsWire
// channel via the YouTube Data API resumable-upload protocol.
// Secrets (YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN) live in
// Worker secrets — never in code, chat, or the repo.
// Auth model: no bearer token. The endpoint only accepts video URLs hosted
// on www.vpsdealswire.com/videos/ (which only the site owner can publish),
// and is rate-limited to a few uploads/day via KV. Worst case abuse is
// re-uploading our own public videos, capped by the daily counter and the
// YouTube API quota.

const YT_VIDEO_PREFIX = "https://www.vpsdealswire.com/videos/";
// Second channel: Tattoo Doodle. Uses a separate refresh token
// (YT_REFRESH_TOKEN_TATTOO) so the VPS channel binding is never disturbed.
// See 2026-10-08 wrong-channel accident; two-token fix designed 2026-10-10,
// deployed 2026-10-11, re-applied 2026-10-16 after a clean-repo redeploy
// on 2026-10-15 wiped it (patch had never been committed).
const YT_VIDEO_PREFIX_TATTOO = "https://www.tattoodoodle.com/assets/videos/";
const YT_SLUG_RE = /^[a-z0-9-]{1,80}$/;
const YT_MAX_UPLOADS_PER_DAY = 5;
const YT_MAX_BYTES = 100 * 1024 * 1024;

async function ytAccessToken(env, useTattoo) {
  const refreshToken = useTattoo ? env.YT_REFRESH_TOKEN_TATTOO : env.YT_REFRESH_TOKEN;
  if (!env.YT_CLIENT_ID || !env.YT_CLIENT_SECRET || !refreshToken)
    throw new Error("youtube_not_configured");
  const r = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      client_id: env.YT_CLIENT_ID,
      client_secret: env.YT_CLIENT_SECRET,
      refresh_token: refreshToken,
    }),
  });
  if (!r.ok) throw new Error("youtube_token_refresh_failed:" + r.status);
  const j = await r.json();
  if (!j.access_token) throw new Error("youtube_token_no_access_token");
  return j.access_token;
}

async function handleYouTubePublish(request, env) {
  if (!ytApiAuth(request, env)) return json({ ok: false, error: "unauthorized" }, 401);
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ ok: false, error: "invalid_json" }, 400);
  }
  const { video_url, title, description, privacy, slug, channel } = body || {};
  const useTattoo = channel === "tattoo";
  const videoPrefix = useTattoo ? YT_VIDEO_PREFIX_TATTOO : YT_VIDEO_PREFIX;
  if (
    typeof video_url !== "string" ||
    !video_url.startsWith(videoPrefix) ||
    !video_url.endsWith(".mp4")
  )
    return json({ ok: false, error: "bad_video_url" }, 400);
  const urlSlug = video_url.slice(videoPrefix.length, -4);
  if (!YT_SLUG_RE.test(urlSlug) || (slug && slug !== urlSlug))
    return json({ ok: false, error: "bad_slug" }, 400);
  if (typeof title !== "string" || !title.trim() || title.length > 100)
    return json({ ok: false, error: "bad_title" }, 400);
  if (typeof description !== "string" || description.length > 5000)
    return json({ ok: false, error: "bad_description" }, 400);
  if (!["private", "unlisted", "public"].includes(privacy))
    return json({ ok: false, error: "bad_privacy" }, 400);

  const day = new Date().toISOString().slice(0, 10);
  const rlKey = "yt:rl:" + day;
  const used = parseInt((await env.SUBS.get(rlKey)) || "0", 10);
  if (used >= YT_MAX_UPLOADS_PER_DAY)
    return json({ ok: false, error: "daily_limit" }, 429);

  let access;
  try {
    access = await ytAccessToken(env, useTattoo);
  } catch (e) {
    return json({ ok: false, error: String((e && e.message) || e) }, 502);
  }

  const vres = await fetch(video_url, { cf: { cacheTtl: 60 } });
  if (!vres.ok) return json({ ok: false, error: "video_fetch_failed:" + vres.status }, 502);
  const buf = await vres.arrayBuffer();
  if (!buf.byteLength || buf.byteLength > YT_MAX_BYTES)
    return json({ ok: false, error: "video_bad_size:" + buf.byteLength }, 400);

  const meta = {
    snippet: {
      title: title.trim(),
      description: description,
      categoryId: "27",
      tags: useTattoo
        ? ["tattoo", "tattoo ideas", "tattoo design", "tattoodoodle"]
        : ["vps", "cheap vps", "vps hosting", "vpsdealswire"],
    },
    status: { privacyStatus: privacy, selfDeclaredMadeForKids: false },
  };
  const init = await fetch(
    "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
    {
      method: "POST",
      headers: {
        Authorization: "Bearer " + access,
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Length": String(buf.byteLength),
        "X-Upload-Content-Type": "video/mp4",
      },
      body: JSON.stringify(meta),
    }
  );
  if (!init.ok) {
    const t = await init.text().catch(() => "");
    return json(
      { ok: false, error: "youtube_init_failed:" + init.status, detail: t.slice(0, 300) },
      502
    );
  }
  const sessionUrl = init.headers.get("location");
  if (!sessionUrl) return json({ ok: false, error: "youtube_no_session" }, 502);

  const up = await fetch(sessionUrl, {
    method: "PUT",
    headers: { "Content-Type": "video/mp4", "Content-Length": String(buf.byteLength) },
    body: buf,
  });
  const ures = await up.json().catch(() => null);
  if (!up.ok || !ures || !ures.id) {
    return json(
      { ok: false, error: "youtube_upload_failed:" + up.status, detail: JSON.stringify(ures).slice(0, 300) },
      502
    );
  }
  await env.SUBS.put(rlKey, String(used + 1), { expirationTtl: 86400 * 2 });
  await env.SUBS.put(
    "yt:last:" + ures.id,
    JSON.stringify({ slug: urlSlug, title: title.trim(), at: new Date().toISOString() }),
    { expirationTtl: 86400 * 90 }
  );
  return json({ ok: true, videoId: ures.id, url: "https://youtu.be/" + ures.id });
}

function ytApiAuth(request, env) {
  if (!env.YT_API_SECRET) return false;
  const h = request.headers.get("Authorization") || "";
  return h === "Bearer " + env.YT_API_SECRET;
}

async function handleYouTubeDelete(request, env) {
  if (!ytApiAuth(request, env)) return json({ ok: false, error: "unauthorized" }, 401);
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ ok: false, error: "invalid_json" }, 400);
  }
  const { video_id } = body || {};
  if (typeof video_id !== "string" || !/^[A-Za-z0-9_-]{11}$/.test(video_id))
    return json({ ok: false, error: "bad_video_id" }, 400);
  let access;
  try {
    access = await ytAccessToken(env);
  } catch (e) {
    return json({ ok: false, error: String((e && e.message) || e) }, 502);
  }
  const r = await fetch(
    "https://www.googleapis.com/youtube/v3/videos?id=" + encodeURIComponent(video_id),
    { method: "DELETE", headers: { Authorization: "Bearer " + access } }
  );
  if (!r.ok && r.status !== 204) {
    const detail = await r.text().catch(() => "");
    return json({ ok: false, error: "youtube_delete_failed:" + r.status, detail: detail.slice(0, 300) }, 502);
  }
  return json({ ok: true, video_id });
}

// ---------- X (Twitter) posting via OAuth 1.0a ----------
// Posts promotional tweets as @liomao for each daily article.
// Secrets (X_CONSUMER_KEY / X_CONSUMER_SECRET / X_ACCESS_TOKEN /
// X_ACCESS_TOKEN_SECRET) live in Worker secrets — never in code, chat,
// or the repo. The /api/x/post endpoint requires the X_POST_SECRET bearer
// (stored in the Worker's secrets and on the operator's machine only),
// and is rate-limited to 5 posts/day via KV.

const X_MAX_POSTS_PER_DAY = 5;

function xPercentEncode(s) {
  return encodeURIComponent(s).replace(/[!'()*]/g, (c) =>
    "%" + c.charCodeAt(0).toString(16).toUpperCase()
  );
}

async function xOAuthHeader(env, method, baseUrl, extraParams) {
  const oauth = {
    oauth_consumer_key: env.X_CONSUMER_KEY,
    oauth_nonce: crypto.randomUUID().replace(/-/g, ""),
    oauth_signature_method: "HMAC-SHA1",
    oauth_timestamp: String(Math.floor(Date.now() / 1000)),
    oauth_token: env.X_ACCESS_TOKEN,
    oauth_version: "1.0",
  };
  const all = { ...oauth, ...(extraParams || {}) };
  const paramStr = Object.keys(all)
    .sort()
    .map((k) => xPercentEncode(k) + "=" + xPercentEncode(all[k]))
    .join("&");
  const baseString =
    method.toUpperCase() +
    "&" +
    xPercentEncode(baseUrl) +
    "&" +
    xPercentEncode(paramStr);
  const signingKey =
    xPercentEncode(env.X_CONSUMER_SECRET) + "&" + xPercentEncode(env.X_ACCESS_TOKEN_SECRET);
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(signingKey),
    { name: "HMAC", hash: "SHA-1" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(baseString));
  const sigB64 = btoa(String.fromCharCode(...new Uint8Array(sig)));
  oauth.oauth_signature = sigB64;
  return (
    "OAuth " +
    Object.keys(oauth)
      .sort()
      .map((k) => xPercentEncode(k) + '="' + xPercentEncode(oauth[k]) + '"')
      .join(", ")
  );
}

function xConfigured(env) {
  return !!(
    env.X_CONSUMER_KEY &&
    env.X_CONSUMER_SECRET &&
    env.X_ACCESS_TOKEN &&
    env.X_ACCESS_TOKEN_SECRET &&
    env.X_POST_SECRET
  );
}

function xAuth(request, env) {
  const h = request.headers.get("Authorization") || "";
  return h === "Bearer " + env.X_POST_SECRET;
}

async function handleXMe(request, env) {
  if (!xConfigured(env)) return json({ ok: false, error: "x_not_configured" }, 500);
  if (!xAuth(request, env)) return json({ ok: false, error: "unauthorized" }, 401);
  const url = "https://api.x.com/2/users/me";
  const r = await fetch(url, {
    headers: { Authorization: await xOAuthHeader(env, "GET", url) },
  });
  const j = await r.json().catch(() => null);
  if (!r.ok) return json({ ok: false, error: "x_api_error:" + r.status, detail: JSON.stringify(j).slice(0, 300) }, 502);
  return json({ ok: true, user: j && j.data ? { id: j.data.id, username: j.data.username, name: j.data.name } : null });
}

async function handleXPost(request, env) {
  if (!xConfigured(env)) return json({ ok: false, error: "x_not_configured" }, 500);
  if (!xAuth(request, env)) return json({ ok: false, error: "unauthorized" }, 401);
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ ok: false, error: "invalid_json" }, 400);
  }
  const { text, dry_run } = body || {};
  if (typeof text !== "string" || !text.trim() || text.length > 280)
    return json({ ok: false, error: "bad_text" }, 400);

  const day = new Date().toISOString().slice(0, 10);
  const rlKey = "x:rl:" + day;
  const used = parseInt((await env.SUBS.get(rlKey)) || "0", 10);
  if (used >= X_MAX_POSTS_PER_DAY)
    return json({ ok: false, error: "daily_limit" }, 429);

  const url = "https://api.x.com/2/tweets";
  const r = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: await xOAuthHeader(env, "POST", url),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ text: dry_run ? "[DRY RUN] " + text : text }),
  });
  const j = await r.json().catch(() => null);
  if (!r.ok)
    return json({ ok: false, error: "x_api_error:" + r.status, detail: JSON.stringify(j).slice(0, 500) }, 502);
  await env.SUBS.put(rlKey, String(used + 1), { expirationTtl: 86400 * 2 });
  const tweetId = j && j.data && j.data.id;
  if (tweetId)
    await env.SUBS.put(
      "x:last:" + tweetId,
      JSON.stringify({ text: text.slice(0, 120), at: new Date().toISOString() }),
      { expirationTtl: 86400 * 90 }
    );
  return json({ ok: true, tweet_id: tweetId || null, dry_run: !!dry_run });
}

// ---------- Google Search Console (read-only) ----------
// Search Analytics API for the 28-day STEP 10 report (daily visitors goal).
// Secrets (GSC_CLIENT_ID / GSC_CLIENT_SECRET / GSC_REFRESH_TOKEN) live in
// Worker secrets — never in code, chat, or the repo. The refresh token needs
// the https://www.googleapis.com/auth/webmasters.readonly scope, granted by
// the site owner via OAuth consent (one-time, on their own machine).
// Endpoints require the same bearer as the YouTube API endpoints.

const GSC_SITE_CANDIDATES = [
  "https://www.vpsdealswire.com/",
  "https://vpsdealswire.com/",
  "sc-domain:vpsdealswire.com",
];
const GSC_SITE_CANDIDATES_TATTOO = [
  "https://www.tattoodoodle.com/",
  "https://tattoodoodle.com/",
  "sc-domain:tattoodoodle.com",
];

async function gscAccessToken(env) {
  if (!env.GSC_CLIENT_ID || !env.GSC_CLIENT_SECRET || !env.GSC_REFRESH_TOKEN)
    throw new Error("gsc_not_configured");
  const r = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      client_id: env.GSC_CLIENT_ID,
      client_secret: env.GSC_CLIENT_SECRET,
      refresh_token: env.GSC_REFRESH_TOKEN,
    }),
  });
  if (!r.ok) throw new Error("gsc_token_refresh_failed:" + r.status);
  const j = await r.json();
  if (!j.access_token) throw new Error("gsc_token_no_access_token");
  return j.access_token;
}

async function gscFetch(access, path, body) {
  const r = await fetch("https://www.googleapis.com/webmasters/v3" + path, {
    method: body ? "POST" : "GET",
    headers: {
      Authorization: "Bearer " + access,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const j = await r.json().catch(() => null);
  return { status: r.status, ok: r.ok, json: j };
}

async function handleGscSites(request, env) {
  if (!ytApiAuth(request, env)) return json({ ok: false, error: "unauthorized" }, 401);
  let access;
  try {
    access = await gscAccessToken(env);
  } catch (e) {
    return json({ ok: false, error: String((e && e.message) || e) }, 502);
  }
  const res = await gscFetch(access, "/sites");
  if (!res.ok)
    return json({ ok: false, error: "gsc_api_error:" + res.status, detail: JSON.stringify(res.json).slice(0, 300) }, 502);
  const sites = (res.json && res.json.siteEntry) || [];
  return json({
    ok: true,
    sites: sites.map((s) => ({ siteUrl: s.siteUrl, permissionLevel: s.permissionLevel })),
  });
}

async function handleGscQuery(request, env) {
  if (!ytApiAuth(request, env)) return json({ ok: false, error: "unauthorized" }, 401);
  const q = new URL(request.url).searchParams;
  const days = Math.min(Math.max(parseInt(q.get("days") || "28", 10) || 28, 1), 90);
  const dim = (q.get("dimension") || "date").toLowerCase();
  const dimension = ["date", "query", "page"].includes(dim) ? dim : "date";
  const siteParam = (q.get("site") || "vps").toLowerCase();
  const siteCandidates = siteParam === "tattoo" ? GSC_SITE_CANDIDATES_TATTOO : GSC_SITE_CANDIDATES;
  const end = new Date();
  end.setDate(end.getDate() - 3); // GSC data lags ~2-3 days
  const start = new Date(end);
  start.setDate(start.getDate() - (days - 1));
  const fmt = (d) => d.toISOString().slice(0, 10);

  let access;
  try {
    access = await gscAccessToken(env);
  } catch (e) {
    return json({ ok: false, error: String((e && e.message) || e) }, 502);
  }

  let siteUrl = null;
  let lastErr = null;
  for (const cand of siteCandidates) {
    const res = await gscFetch(access, "/sites/" + encodeURIComponent(cand) + "/searchAnalytics/query", {
      startDate: fmt(start),
      endDate: fmt(end),
      dimensions: [dimension],
      rowLimit: 1000,
    });
    if (res.ok) {
      siteUrl = cand;
      var rows = (res.json && res.json.rows) || [];
      break;
    }
    lastErr = "gsc_api_error:" + res.status;
  }
  if (!siteUrl)
    return json({ ok: false, error: lastErr || "gsc_no_site", detail: "tried: " + siteCandidates.join(", ") }, 502);

  let clicks = 0;
  let impressions = 0;
  for (const row of rows) {
    clicks += row.clicks || 0;
    impressions += row.impressions || 0;
  }
  const out = {
    ok: true,
    site: siteUrl,
    startDate: fmt(start),
    endDate: fmt(end),
    dimension,
    total_clicks: Math.round(clicks),
    total_impressions: Math.round(impressions),
  };
  if (dimension === "date") {
    out.days_with_data = rows.length;
    out.avg_daily_clicks = rows.length ? Math.round((clicks / rows.length) * 10) / 10 : 0;
    out.avg_daily_impressions = rows.length ? Math.round((impressions / rows.length) * 10) / 10 : 0;
    out.last_14_days = rows.slice(-14).map((r) => ({
      date: r.keys[0],
      clicks: Math.round(r.clicks || 0),
      impressions: Math.round(r.impressions || 0),
    }));
  } else {
    rows.sort((a, b) => (b.impressions || 0) - (a.impressions || 0));
    out.top_rows = rows.slice(0, 50).map((r) => ({
      [dimension]: r.keys[0],
      clicks: Math.round(r.clicks || 0),
      impressions: Math.round(r.impressions || 0),
      ctr: r.ctr,
      position: Math.round((r.position || 0) * 10) / 10,
    }));
  }
  return json(out);
}
// Management-created capability jobs. Tokens and OAuth secrets never leave the server.
const YTP_CHANNELS = Object.freeze({
  tattoo: { id: "UCQ8j4vfF-Oosb0PVlaXdvmA", site: "https://www.tattoodoodle.com", prefix: YT_VIDEO_PREFIX_TATTOO },
  vps: { id: "UCfgVJrtBJSeViu95AnaQxyA", site: SITE, prefix: YT_VIDEO_PREFIX },
});
const YTP_MAX_BYTES = 24 * 1024 * 1024;
const YTP_ID = /^[a-z0-9][a-z0-9-]{1,79}$/;
const YTP_UUID = /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/;

function ytpError(code) { throw new Error(code); }
async function ytpBytes(response, limit) {
  const declared = Number(response.headers.get("content-length") || 0);
  if (declared > limit) ytpError("response_too_large");
  const reader = response.body?.getReader();
  if (!reader) ytpError("empty_response");
  const chunks = []; let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit) ytpError("response_too_large");
      chunks.push(value);
    }
  } catch (error) { await reader.cancel().catch(() => {}); throw error; }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return bytes;
}
async function ytpJson(response) {
  const raw = await ytpBytes(response, 1024 * 1024);
  const parsed = JSON.parse(new TextDecoder().decode(raw));
  if (!response.ok) {
    const reason = parsed.error?.errors?.[0]?.reason;
    ytpError("youtube_read_" + response.status + (typeof reason === "string" && /^[A-Za-z0-9_-]+$/.test(reason) ? ":" + reason : ""));
  }
  return parsed;
}
async function ytpApi(access, path) {
  return ytpJson(await fetch("https://www.googleapis.com/youtube/v3/" + path, {
    headers: { Authorization: "Bearer " + access }, signal: AbortSignal.timeout(30000),
  }));
}
async function ytpGrant(env, channel) {
  const refresh = channel === "tattoo" ? env.YT_REFRESH_TOKEN_TATTOO : env.YT_REFRESH_TOKEN;
  if (!env.YT_CLIENT_ID || !env.YT_CLIENT_SECRET || !refresh) ytpError("youtube_not_configured");
  const response = await fetch("https://oauth2.googleapis.com/token", { method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ grant_type: "refresh_token", client_id: env.YT_CLIENT_ID, client_secret: env.YT_CLIENT_SECRET, refresh_token: refresh }), signal: AbortSignal.timeout(30000) });
  if (!response.ok) { await response.body?.cancel(); ytpError("youtube_token_refresh_failed_" + response.status); }
  const data = await ytpJson(response);
  if (!data.access_token) ytpError("youtube_token_missing");
  let scope = data.scope;
  if (typeof scope !== "string") {
    // Google is the token issuer. Never log or return this URL or token.
    const info = await fetch("https://oauth2.googleapis.com/tokeninfo?access_token=" + encodeURIComponent(data.access_token), { signal: AbortSignal.timeout(30000) });
    if (!info.ok) { await info.body?.cancel(); ytpError("youtube_scope_unverified"); }
    scope = (await ytpJson(info)).scope;
  }
  const upload = ["youtube.upload", "youtube", "youtube.force-ssl", "youtubepartner"].map(s => "https://www.googleapis.com/auth/" + s);
  return { access: data.access_token, uploadScopeGranted: typeof scope === "string" && scope.split(/\s+/).some(s => upload.includes(s)) };
}
function ytpValidate(job) {
  if (!job || !YTP_UUID.test(job.id) || !Object.hasOwn(YTP_CHANNELS, job.channel)) ytpError("bad_job");
  if (!["inspect", "upload", "verify"].includes(job.operation)) ytpError("bad_operation");
  if (!Number.isFinite(Date.parse(job.expiresAt)) || Date.parse(job.expiresAt) <= Date.now()) ytpError("expired_job");
  if (!/^[a-f0-9]{64}$/.test(job.tokenSha256 || "")) ytpError("bad_job_auth");
  const config = YTP_CHANNELS[job.channel];
  if (job.expectedChannelId !== config.id) ytpError("bad_expected_channel");
  if (job.operation === "inspect") return config;
  if (!YTP_ID.test(job.contentId || "")) ytpError("bad_content_id");
  if (job.operation === "verify") return config;
  if (typeof job.videoUrl !== "string" || !job.videoUrl.startsWith(config.prefix) || !job.videoUrl.endsWith(".mp4")) ytpError("bad_video_url");
  if (!YT_SLUG_RE.test(job.videoUrl.slice(config.prefix.length, -4))) ytpError("bad_video_slug");
  if (!/^[a-f0-9]{64}$/.test(job.mediaSha256 || "")) ytpError("bad_media_sha256");
  if (typeof job.title !== "string" || !job.title.trim() || job.title.length > 100 || /[<>]/.test(job.title)) ytpError("bad_title");
  if (typeof job.description !== "string" || !job.description.trim() || job.description.length > 5000) ytpError("bad_description");
  const landing = new URL(job.description.split("\n")[0].trim());
  if (landing.origin !== config.site || landing.searchParams.get("utm_source") !== "youtube" || landing.searchParams.get("utm_content") !== job.contentId) ytpError("bad_landing_utm");
  if (!Number.isFinite(Date.parse(job.publishAt)) || Date.parse(job.publishAt) < Date.now() + 15 * 60000 || Date.parse(job.publishAt) > Date.now() + 31 * 86400000) ytpError("bad_publish_time");
  if (job.reviewed !== true) ytpError("media_not_reviewed");
  return config;
}
async function handleYouTubeJob(request, env) {
  // The public caller cannot choose any payload. Only Cloudflare management access
  // can create the immutable envelope in KV; the short-lived capability is private.
  if (request.method !== "POST") return json({ ok: false, error: "method_not_allowed" }, 405);
  const id = new URL(request.url).pathname.slice("/api/youtube/jobs/".length);
  if (!YTP_UUID.test(id)) return json({ ok: false, error: "not_found" }, 404);
  try {
    const job = await env.SUBS.get("yt:job:" + id, "json");
    if (!job || job.id !== id) return json({ ok: false, error: "not_found" }, 404);
    ytpValidate(job);
    const auth = request.headers.get("Authorization") || "";
    if (!/^Bearer [a-f0-9]{64}$/.test(auth)) return json({ ok: false, error: "unauthorized" }, 401);
    const actual = new TextEncoder().encode(await sha256(auth.slice(7)));
    const expected = new TextEncoder().encode(job.tokenSha256);
    if (!crypto.subtle.timingSafeEqual(actual, expected)) return json({ ok: false, error: "unauthorized" }, 401);
    if (!env.YT_PUBLISHER) return json({ ok: false, error: "publisher_not_configured" }, 503);
    const result = await env.YT_PUBLISHER.getByName(job.channel).execute(job);
    await env.SUBS.put("yt:result:" + id, JSON.stringify(result), { expirationTtl: 90 * 86400 });
    return json(result, result.ok ? 200 : 409);
  } catch (error) {
    const message = String(error?.message || "job_failed");
    const safe = /^[a-z0-9_:]+$/i.test(message) ? message : "job_failed_check_server_record";
    return json({ ok: false, error: safe }, safe === "expired_job" ? 410 : 400);
  }
}
async function ytpInventory(access, config) {
  const identity = await ytpApi(access, "channels?part=snippet,contentDetails&mine=true");
  const channel = identity.items?.find(item => item.id === config.id);
  if (identity.items?.length !== 1 || !channel) ytpError("channel_identity_mismatch");
  const playlist = channel.contentDetails?.relatedPlaylists?.uploads;
  if (!playlist) ytpError("missing_uploads_playlist");
  const videos = []; let pageToken;
  for (let page = 0; page < 10; page++) {
    const list = await ytpApi(access, "playlistItems?part=contentDetails&maxResults=50&playlistId=" + encodeURIComponent(playlist) + (pageToken ? "&pageToken=" + encodeURIComponent(pageToken) : ""));
    const ids = (list.items || []).map(item => item.contentDetails?.videoId).filter(Boolean);
    if (ids.length) {
      const details = await ytpApi(access, "videos?part=snippet,status,processingDetails&maxResults=50&id=" + ids.map(encodeURIComponent).join(","));
      for (const video of details.items || []) {
        if (video.snippet?.channelId !== config.id) ytpError("inventory_channel_mismatch");
        videos.push({ id: video.id, channelId: video.snippet.channelId, title: video.snippet.title,
          description: video.snippet.description || "", publishedAt: video.snippet.publishedAt,
          privacy: video.status?.privacyStatus, publishAt: video.status?.publishAt,
          processing: video.processingDetails?.processingStatus, uploadStatus: video.status?.uploadStatus });
      }
    }
    pageToken = list.nextPageToken;
    if (!pageToken) return { channelId: channel.id, channelTitle: channel.snippet?.title, inventoryComplete: true, videos };
  }
  ytpError("inventory_requires_more_pages");
}
function ytpHasContent(video, contentId, site) {
  return (video.description || "").split(/\s+/).some(word => {
    try { const u = new URL(word); return u.origin === site && u.searchParams.get("utm_source") === "youtube" && u.searchParams.get("utm_content") === contentId; }
    catch { return false; }
  });
}
export class YouTubePublisher extends DurableObject {
  // One durable coordinator per channel. Sync SQLite-backed KV and an atomic
  // reservation survive retries, concurrent requests and instance eviction.
  async execute(job) {
    const config = ytpValidate(job), kv = this.ctx.storage.kv;
    const cached = kv.get("job:" + job.id);
    if (cached && job.operation !== "verify") return cached;
    const pending = { ok: false, jobId: job.id, channel: job.channel, state: "running", at: new Date().toISOString() };
    kv.put("job:" + job.id, pending);
    let attempt;
    try {
      const grant = await ytpGrant(this.env, job.channel), access = grant.access;
      const inventory = await ytpInventory(access, config);
      if (job.operation === "inspect") return this.finish(job, { ok: true, state: "channel_verified", uploadScopeGranted: grant.uploadScopeGranted, ...inventory });
      const key = "asset:" + job.contentId;
      const prior = kv.get(key);
      const matches = inventory.videos.filter(video => ytpHasContent(video, job.contentId, config.site));
      if (matches.length > 1) ytpError("duplicate_content_requires_review");
      if (prior?.videoId || matches.length === 1) {
        const videoId = prior?.videoId || matches[0].id;
        if (matches.length && matches[0].id !== videoId) ytpError("content_id_conflict");
        const stored = { ...(prior || { contentId: job.contentId, state: "adopted_existing", publishAt: matches[0].publishAt }), videoId };
        kv.put(key, stored);
        return await this.verify(job, stored, access, config);
      }
      if (prior) return this.finish(job, { ok: false, state: prior.state, error: "previous_attempt_requires_reconciliation", contentId: job.contentId });
      if (job.operation === "verify") ytpError("no_upload_record");
      if (!grant.uploadScopeGranted) ytpError("youtube_upload_scope_missing");
      const slug = job.videoUrl.slice(config.prefix.length, -4);
      // Legacy records have no channel field. Be conservative across both sites.
      let cursor;
      do {
        const page = await this.env.SUBS.list({ prefix: "yt:last:", ...(cursor ? { cursor } : {}) });
        for (const item of page.keys) {
          const receipt = await this.env.SUBS.get(item.name, "json");
          if (receipt?.slug === slug) ytpError("legacy_slug_already_uploaded");
        }
        if (!page.list_complete && !page.cursor) ytpError("legacy_inventory_incomplete");
        cursor = page.list_complete ? undefined : page.cursor;
      } while (cursor);
      const landing = job.description.split("\n")[0].trim();
      const page = await fetch(landing, { redirect: "error", signal: AbortSignal.timeout(30000) });
      await page.body?.cancel();
      if (page.status !== 200) ytpError("landing_not_live");
      const media = await fetch(job.videoUrl, { redirect: "error", signal: AbortSignal.timeout(90000) });
      if (!media.ok || !(media.headers.get("content-type") || "").toLowerCase().startsWith("video/mp4")) { await media.body?.cancel(); ytpError("media_not_available"); }
      const bytes = await ytpBytes(media, YTP_MAX_BYTES);
      if (bytes.byteLength < 16 || new TextDecoder().decode(bytes.slice(4, 8)) !== "ftyp") ytpError("invalid_mp4");
      const hash = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map(b => b.toString(16).padStart(2, "0")).join("");
      if (hash !== job.mediaSha256) ytpError("media_hash_mismatch");
      if (Date.parse(job.publishAt) < Date.now() + 5 * 60000) ytpError("publish_time_too_close");
      attempt = { contentId: job.contentId, channelId: config.id, jobId: job.id, state: "upload_uncertain", videoUrl: job.videoUrl,
        mediaSha256: hash, title: job.title, description: job.description, publishAt: job.publishAt, at: new Date().toISOString() };
      this.ctx.storage.transactionSync(() => {
        if (kv.get(key)) ytpError("concurrent_content_reservation");
        if (kv.get("hash:" + hash) || kv.get("slug:" + slug)) ytpError("duplicate_media_or_slug");
        const day = new Date().toISOString().slice(0, 10), count = kv.get("daily:" + day) || 0;
        if (count >= 2) ytpError("daily_channel_limit");
        kv.put(key, attempt); kv.put("hash:" + hash, job.contentId); kv.put("slug:" + slug, job.contentId); kv.put("daily:" + day, count + 1);
      });
      await this.ctx.storage.sync(); // Persist reservation before any YouTube write.
      const init = await fetch("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", {
        method: "POST", headers: { Authorization: "Bearer " + access, "Content-Type": "application/json; charset=UTF-8",
          "X-Upload-Content-Length": String(bytes.byteLength), "X-Upload-Content-Type": "video/mp4" },
        body: JSON.stringify({ snippet: { title: job.title.trim(), description: job.description, categoryId: "27" },
          status: { privacyStatus: "private", publishAt: job.publishAt, selfDeclaredMadeForKids: false } }), signal: AbortSignal.timeout(30000),
      });
      if (!init.ok) { await init.body?.cancel(); ytpError("youtube_init_failed_" + init.status); }
      const session = init.headers.get("location"); await init.body?.cancel();
      if (!session || !/^https:\/\/(?:www\.)?googleapis\.com\//.test(session)) ytpError("invalid_upload_session");
      const upload = await fetch(session, { method: "PUT", headers: { "Content-Type": "video/mp4", "Content-Length": String(bytes.byteLength) }, body: bytes, signal: AbortSignal.timeout(90000) });
      const data = await ytpJson(upload);
      if (!/^[A-Za-z0-9_-]{11}$/.test(data.id || "")) ytpError("upload_response_missing_id");
      attempt = { ...attempt, videoId: data.id, state: "uploaded_unverified" }; kv.put(key, attempt);
      await this.ctx.storage.sync();
      return await this.verify(job, attempt, access, config);
    } catch (error) {
      const raw = String(error?.message || "publisher_error");
      const safe = /^[a-z0-9_:]+$/i.test(raw) ? raw : "publisher_error_reconcile_before_retry";
      const current = job.contentId ? kv.get("asset:" + job.contentId) : null;
      return this.finish(job, { ok: false, state: current?.state || "preflight_failed", error: safe, ...(current?.videoId ? { videoId: current.videoId } : {}) });
    }
  }
  async verify(job, asset, access, config) {
    const data = await ytpApi(access, "videos?part=snippet,status,processingDetails&id=" + encodeURIComponent(asset.videoId));
    const video = data.items?.[0];
    if (!video || video.id !== asset.videoId || video.snippet?.channelId !== config.id) ytpError("video_identity_unverified");
    if (!ytpHasContent({ description: video.snippet.description }, job.contentId, config.site)) ytpError("video_utm_unverified");
    if (asset.title && (video.snippet.title !== asset.title.trim() || video.snippet.description !== asset.description)) ytpError("video_metadata_mismatch");
    const privacy = video.status?.privacyStatus, publishAt = video.status?.publishAt;
    const processing = video.processingDetails?.processingStatus;
    let state = "uploaded_unverified";
    if (["failed", "terminated"].includes(processing) || ["failed", "rejected", "deleted"].includes(video.status?.uploadStatus)) state = "processing_failed";
    else if (privacy === "public" && (!asset.publishAt || Date.parse(asset.publishAt) <= Date.now())) state = "published";
    else if (privacy === "private" && asset.publishAt && publishAt && Date.parse(publishAt) === Date.parse(asset.publishAt)) state = "scheduled";
    const result = { ...asset, channelId: config.id, videoId: video.id, videoUrl: "https://www.youtube.com/watch?v=" + video.id,
      state, privacy, processing, verifiedPublishAt: publishAt || null, verifiedAt: new Date().toISOString() };
    if (state === "published") {
      const time = Date.parse(video.snippet.publishedAt);
      if (!Number.isFinite(time)) ytpError("publication_time_unverified");
      result.actualPublishedAt = new Date(time).toISOString();
      result.review7At = new Date(time + 7 * 86400000).toISOString(); result.review28At = new Date(time + 28 * 86400000).toISOString();
    }
    this.ctx.storage.kv.put("asset:" + job.contentId, result);
    return this.finish(job, { ok: ["scheduled", "published"].includes(state), ...result });
  }
  finish(job, result) {
    const safe = { jobId: job.id, channel: job.channel, ...result };
    this.ctx.storage.kv.put("job:" + job.id, safe);
    return safe;
  }
}
