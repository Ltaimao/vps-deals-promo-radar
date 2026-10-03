/* Cloudflare Pages Function: Accept: text/markdown content negotiation.
 *
 * The scanner (isitagentready.com) requests the homepage with
 * `Accept: text/markdown` and expects `Content-Type: text/markdown`.
 * The Markdown body is prebuilt by build.py into /index.md from the same
 * real data as the HTML page, so both representations stay consistent.
 * Ordinary requests fall through to the static asset untouched.
 */
export async function onRequest({ request, env, next }) {
  const accept = request.headers.get("Accept") || "";
  if (accept.includes("text/markdown")) {
    try {
      const mdUrl = new URL("/index.md", request.url);
      const res = await env.ASSETS.fetch(new Request(mdUrl, request));
      if (res.ok) {
        const body = await res.text();
        return new Response(body, {
          headers: {
            "Content-Type": "text/markdown; charset=utf-8",
            "Cache-Control": "public, max-age=300",
            "Vary": "Accept",
          },
        });
      }
    } catch (e) {
      // fall through to static HTML on any edge failure
    }
  }
  return next();
}
