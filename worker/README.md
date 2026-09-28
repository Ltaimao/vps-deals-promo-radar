# vpsdealswire-api worker

Subscription (double opt-in) + price-drop alert API for vpsdealswire.com.
Deployed as a standalone Worker (Pages Functions can't run cron triggers).

- `api.js` — the worker. `POST /api/subscribe`, `GET /api/confirm`,
  `GET /api/unsubscribe`, `GET /api/health`, plus a `scheduled` handler
  (every 6h, at :30) that emails active subscribers about new lowest prices.
- KV namespace `vpsdealswire-subscribers` holds pending/active subscriptions.
- Sending goes through the Cloudflare Email Sending `send_email` binding
  (transactional only: confirmations + alerts the user asked for).
- Routes: `www.vpsdealswire.com/api/*` and `vpsdealswire.com/api/*`.

## Deploy

Not part of the Pages build — deploy explicitly:

    python3 worker/deploy.py worker/api.js

Cron schedule is set separately via the API (currently `30 */6 * * *`).
