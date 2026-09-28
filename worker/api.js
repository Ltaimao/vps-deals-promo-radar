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
  await env.EMAIL.send({
    from: FROM,
    to,
    subject,
    text,
    html,
  });
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

  // fresh drops: current price is a NEW ALL-TIME LOW for the deal
  const drops = [];
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
    if (cur >= prevLow) continue;
    const alerted = parseFloat((await env.SUBS.get("alerted:" + key)) || "Infinity");
    if (cur >= alerted) continue; // already told them about this low
    drops.push({
      key,
      provider: d.provider_name,
      slug: d.provider_slug,
      title: d.title,
      cur,
      prev: prevLow,
      currency: d.currency || "USD",
      url: d.offer_url || d.source_url,
    });
  }
  if (!drops.length) {
    await env.SUBS.put("meta:last_cron", now + " no-drops");
    return;
  }

  // collect active subscribers (KV list, paginated)
  const subs = [];
  let cursor;
  do {
    const list = await env.SUBS.list({ prefix: "sub:", cursor });
    for (const k of list.keys) {
      const sub = await env.SUBS.get(k.name, "json");
      if (sub && sub.status === "active" && EMAIL_RE.test(sub.email)) subs.push(sub);
    }
    cursor = list.list_complete ? undefined : list.cursor;
  } while (cursor);

  const sym = { USD: "$", EUR: "€", GBP: "£" };
  for (const sub of subs) {
    const unsubLink = SITE + "/api/unsubscribe?token=" + sub.unsub_token;
    const lines = drops.map(
      (x) =>
        "- " + x.provider + " — " + x.title + ": now " +
        (sym[x.currency] || x.currency + " ") + x.cur + "/mo (was " +
        (sym[x.currency] || x.currency + " ") + x.prev + ")"
    );
    const text =
      "Price drops on VPS Deals Wire:\n\n" + lines.join("\n") + "\n\n" +
      drops.map((x) => x.provider + ": " + SITE + "/providers/" + x.slug + "/").join("\n") +
      "\n\nUnsubscribe any time (one click, immediate):\n" + unsubLink;
    const html =
      "<p><strong>Price drops on VPS Deals Wire:</strong></p><ul>" +
      drops.map(
        (x) =>
          "<li>" + escapeHtml(x.provider) + " — " + escapeHtml(x.title) + ": now <strong>" +
          escapeHtml((sym[x.currency] || x.currency + " ") + x.cur) + "/mo</strong> (was " +
          escapeHtml((sym[x.currency] || x.currency + " ") + x.prev) + ") " +
          "<a href=\"" + SITE + "/providers/" + x.slug + "/\">view</a></li>"
      ).join("") + "</ul>" +
      "<p><a href=\"" + unsubLink + "\">Unsubscribe</a> — one click, immediate.</p>";
    const subject =
      drops.length === 1
        ? "Price drop: " + drops[0].provider + " now " +
          (sym[drops[0].currency] || "") + drops[0].cur + "/mo"
        : drops.length + " VPS price drops";
    try {
      await sendMail(env, sub.email, subject, text, html);
    } catch {
      // per-recipient failure must not block the rest
    }
  }
  for (const x of drops) {
    await env.SUBS.put("alerted:" + x.key, String(x.cur));
  }
  await env.SUBS.put("meta:last_cron", now + " drops=" + drops.length);
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return json({ ok: true });
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
      return json({ ok: true, version: "phase4-1" });
    }
    return json({ ok: false, error: "not_found" }, 404);
  },
  async scheduled(event, env, ctx) {
    ctx.waitUntil(handleScheduled(env));
  },
};
