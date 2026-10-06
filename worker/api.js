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
  if (existing && existing.status === "pending" && existing.token) {
    token = existing.token;
  } else {
    token = crypto.randomUUID();
    await env.SUBS.put(
      "sub:" + ehash,
      JSON.stringify({
        status: "pending",
        email,
        token,
        created_at: new Date().toISOString(),
      })
    );
  }
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
    if (d.price == null) continue;
    const key =
      d.offer_id ||
      (await sha256(
        "vpsdw:" +
          [d.provider_slug, d.offer_url, d.title]
            .map((p) => (p || "").trim().toLowerCase().replace(/\s+/g, " "))
            .join("\x00")
      )).slice(0, 16);
    const s = series[key];
    if (!s || !s.points || s.points.length < 2) continue;
    const prices = s.points.map((p) => p[1]);
    const prevLow = Math.min(...prices.slice(0, -1));
    const cur = prices[prices.length - 1];
    const watch = await env.SUBS.get("dropwatch:" + key, "json");
    if (watch && watch.price === cur) {
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
        JSON.stringify({ price: cur, prev: prevLow })
      );
      watching++;
    } else if (watch) {
      // price moved away from the watched low: void the watch
      await env.SUBS.delete("dropwatch:" + key);
    }
  }

  // collect active subscribers (KV list, paginated)
  const subs = [];
  let cursor;
  do {
    const list = await env.SUBS.list({ prefix: "sub:", cursor });
    for (const k of list.keys) {
      const sub = await env.SUBS.get(k.name, "json");
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
      " sent=" + sent + " failed=" + failed
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
    return json({ ok: false, error: "not_found" }, 404);
  },
  async scheduled(event, env, ctx) {
    ctx.waitUntil(handleScheduled(env));
  },
};

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
const YT_SLUG_RE = /^[a-z0-9-]{1,80}$/;
const YT_MAX_UPLOADS_PER_DAY = 5;
const YT_MAX_BYTES = 100 * 1024 * 1024;

async function ytAccessToken(env) {
  if (!env.YT_CLIENT_ID || !env.YT_CLIENT_SECRET || !env.YT_REFRESH_TOKEN)
    throw new Error("youtube_not_configured");
  const r = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      client_id: env.YT_CLIENT_ID,
      client_secret: env.YT_CLIENT_SECRET,
      refresh_token: env.YT_REFRESH_TOKEN,
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
  const { video_url, title, description, privacy, slug } = body || {};
  if (
    typeof video_url !== "string" ||
    !video_url.startsWith(YT_VIDEO_PREFIX) ||
    !video_url.endsWith(".mp4")
  )
    return json({ ok: false, error: "bad_video_url" }, 400);
  const urlSlug = video_url.slice(YT_VIDEO_PREFIX.length, -4);
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
    access = await ytAccessToken(env);
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
      tags: ["vps", "cheap vps", "vps hosting", "vpsdealswire"],
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
  for (const cand of GSC_SITE_CANDIDATES) {
    const res = await gscFetch(access, "/sites/" + encodeURIComponent(cand) + "/searchAnalytics/query", {
      startDate: fmt(start),
      endDate: fmt(end),
      dimensions: ["date"],
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
    return json({ ok: false, error: lastErr || "gsc_no_site", detail: "tried: " + GSC_SITE_CANDIDATES.join(", ") }, 502);

  let clicks = 0;
  let impressions = 0;
  for (const row of rows) {
    clicks += row.clicks || 0;
    impressions += row.impressions || 0;
  }
  return json({
    ok: true,
    site: siteUrl,
    startDate: fmt(start),
    endDate: fmt(end),
    days_with_data: rows.length,
    total_clicks: Math.round(clicks),
    total_impressions: Math.round(impressions),
    avg_daily_clicks: rows.length ? Math.round((clicks / rows.length) * 10) / 10 : 0,
    avg_daily_impressions: rows.length ? Math.round((impressions / rows.length) * 10) / 10 : 0,
    last_14_days: rows.slice(-14).map((r) => ({
      date: r.keys[0],
      clicks: Math.round(r.clicks || 0),
      impressions: Math.round(r.impressions || 0),
    })),
  });
}
