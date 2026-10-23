# vpsdealswire-api worker

Subscription (double opt-in) + price-drop alert API for vpsdealswire.com.
Deployed as a standalone Worker (Pages Functions can't run cron triggers).

- `api.js` — the worker. `POST /api/subscribe`, `GET /api/confirm`,
  `GET /api/unsubscribe`, `GET /api/health`, plus a `scheduled` handler
  (every 6h, at :30) that emails active subscribers about new lowest prices.
- KV namespace `vpsdealswire-subscribers` holds pending/active subscriptions.
- Sending goes through Resend (`https://api.resend.com/emails`) using the Worker secret `RESEND_API_KEY` (confirmations and requested price alerts only). The former Cloudflare `send_email` binding is not used.
- Routes: `www.vpsdealswire.com/api/*` and `vpsdealswire.com/api/*`.

## Deploy

Not part of the Pages build — deploy explicitly:

    # Use the deployment instructions in docs/OPERATIONS.md; the old surrogate
    # credential helper is not available in the current cloud environment.

Cron schedule is set separately via the API (currently `30 */6 * * *`).

Additional routes in api.js include MCP and authenticated operations integrations. Never replace a live Worker from an older file or omit its existing bindings. A successful Pages deployment does not deploy this Worker or prove email delivery.

Pending fixes in the repository require a separate Worker release: email + confirmation records share a 30-day TTL for new/resubmitted pending requests; confirmed subscriptions have no pending TTL. Alerts compare only explicit monthly history in the same currency and require distinct snapshot IDs. Existing legacy pending records need a separate retention review. See tests/test_worker.mjs.
