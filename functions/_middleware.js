/* Cloudflare Pages middleware: agent-discovery headers + markdown negotiation.
 *
 * _headers proved unreliable for these paths, so this middleware sets them
 * deterministically in code. It only touches the listed discovery paths and
 * the homepage; every other request passes through untouched.
 */
const LINK =
  '</.well-known/api-catalog>; rel="api-catalog", ' +
  '</openapi.json>; rel="service-desc", ' +
  '</ai/>; rel="service-doc", ' +
  '</auth.md>; rel="describedby"';

// Exact-path header fixes: [Content-Type, Access-Control-Allow-Origin]
const PATH_HEADERS = {
  "/.well-known/api-catalog": ["application/linkset+json", null],
  "/.well-known/ai-catalog.json": [null, "*"],
  "/auth.md": ["text/markdown; charset=utf-8", null],
  "/llms.txt": ["text/markdown; charset=utf-8", null],
  "/ai/skills/site-lookup/SKILL.md": ["text/markdown; charset=utf-8", null],
};

function withHeaders(res, set) {
  const headers = new Headers(res.headers);
  for (const [k, v] of Object.entries(set)) {
    if (v !== null && v !== undefined) headers.set(k, v);
  }
  return new Response(res.body, {
    status: res.status,
    statusText: res.statusText,
    headers,
  });
}

export async function onRequest({ request, env, next }) {
  const url = new URL(request.url);
  const path = url.pathname;

  // 1. Markdown negotiation for the homepage (scanner: Accept: text/markdown).
  //    Body is prebuilt by build.py into /index.md from the same real data.
  if (path === "/") {
    const accept = request.headers.get("Accept") || "";
    if (accept.includes("text/markdown")) {
      try {
        const mdRes = await env.ASSETS.fetch(new Request(new URL("/index.md", url), request));
        if (mdRes.ok) {
          return new Response(await mdRes.text(), {
            headers: {
              "Content-Type": "text/markdown; charset=utf-8",
              "Cache-Control": "public, max-age=300",
              Vary: "Accept",
              Link: LINK,
            },
          });
        }
      } catch (e) {
        /* fall through to static HTML */
      }
    }
    return withHeaders(await next(), { Link: LINK });
  }

  // 2. Fixed content types / CORS for discovery files.
  const fix = PATH_HEADERS[path];
  if (fix) {
    const res = await next();
    const set = {};
    if (fix[0]) set["Content-Type"] = fix[0];
    if (fix[1]) set["Access-Control-Allow-Origin"] = fix[1];
    return withHeaders(res, set);
  }

  return next();
}
