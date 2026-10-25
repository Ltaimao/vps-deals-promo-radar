# Managed YouTube publication

The owner authorized resolving autonomous publishing on 2026-10-25. This path uses the existing server-side OAuth grants without exporting, resetting or replacing any existing secret. The old local shared caller credential is unnecessary for this path.

## Trust and coordination

Only authorized Cloudflare management access can create a `yt:job:<UUID>` envelope in the existing SUBS namespace. A public request cannot choose the payload. An independently generated 256-bit capability is kept in a private local file; only its SHA-256 is stored with the envelope. Invocation requires that capability in Authorization, uses constant-time comparison, rejects expired jobs and never logs the credential. Default expiry is one hour; use a matching KV TTL. No job capability belongs in source control or a chat message.

The new `YT_PUBLISHER` binding uses one SQLite-backed Durable Object per channel. Its durable attempt, content, source-slug and file-hash records prevent concurrent/repeated uploads. Reservation is persisted before YouTube writes. A timeout/ambiguous response locks the attempt for reconciliation, not blind resubmission. This is conservative at-most-once submission: a blocked ambiguous attempt may require evidence-based repair rather than an automatic second upload. Old KV receipts are an additional conservative duplicate check, not the concurrency lock.

Channel identity is read from the actual OAuth token with `channels.list(mine=true)` and matched to the explicit expected channel ID. Every existing upload is read with authenticated playlist/video APIs before a new upload (up to 500 items; a longer unresolved inventory blocks uploading). The tattoo refresh token can only pass the Tattoo Doodle identity check; VPS can only pass its own. Token-variable presence alone is not readiness. A scope/refresh failure is a genuine authorization issue and must be reported without trying an upload as a test.

## Operations

`inspect` verifies the channel and reads its actual upload inventory without creating or editing any video. `upload` accepts reviewed MP4 up to 24 MiB from the existing site-specific media prefix, checks source SHA-256, live UTM landing page and a future schedule. `verify` reconciles an existing attempt and reads back video ownership, metadata, privacy, native schedule and processing status. No deletion, arbitrary upload origin or existing-video metadata editing is implemented by this path.

Uploads explicitly use private visibility plus future `status.publishAt` ([YouTube documentation](https://developers.google.com/youtube/data/reference/rest/v3/videos#status.publishAt)). Native YouTube scheduling removes a dependency on an exact-time chat/cron run. A scheduling response is not public publication. Readback must show the actual ID, matching channel, metadata and native private schedule to report scheduled; only public readback permits published. Actual publication timestamp determines +7/+28-day checks. Processing/rejection/private-without-schedule/early-public states are kept distinct.

Do not use historical video files as upload tests. The first real upload must be the first reviewed new marketing video; source scripts are not finished media. No claim that the Google write scope or an actual upload has succeeded may be made from `inspect` alone.

## Client procedure

1. Create a short-lived job outside the repository:

   ```sh
   node worker/youtube-job.cjs create --channel tattoo --operation inspect --output /tmp/tattoo-inspect.json
   # VPS: --channel vps. Verify: --operation verify --content-id td-y001.
   # Upload additionally requires --manifest /private/reviewed.json --media /private/final.mp4.
   ```

2. Through the already-connected Cloudflare management tool, PUT only the file's `envelope` as JSON bytes to `/accounts/<account>/storage/kv/namespaces/<SUBS>/values/yt%3Ajob%3A<UUID>` with `expiration_ttl=3600`. Never return the capability or any OAuth secret in tool output. Existing SUBS namespace: `4d8d62c95b204b4e9eeb5aa5e6c77351`; account `41adaf2bce076e1cefb1a8ad67b51856`.
3. Invoke using the real browser client (no forged User-Agent):

   ```sh
   node worker/youtube-job.cjs invoke --job /tmp/tattoo-inspect.json
   ```

   It uses a same-origin request to the public API. Results are saved privately; stdout contains only a summary. An immediate KV miss may be propagation delay; retry the same job identity after allowing replication, never create a replacement upload job to guess what happened.

4. Keep private/unlisted inventory and capability files outside public repositories. Persist only necessary publication evidence and aggregate inventory counts. Future verify jobs use a fresh capability and the same stable content ID. Durable records are the source of upload-attempt identity.

The reviewed upload manifest contains `contentId`, `videoUrl`, `mediaSha256`, `title`, `description` (first line is the correct same-site URL with utm_source=youtube and the content ID), `publishAt` (ISO timestamp with timezone, 15 minutes to 31 days ahead) and `reviewed:true`. This review flag must follow actual media/audio/rights review, not script review. Submit at most two new videos per channel per UTC day. Keep meaningful derivatives separately reviewed and identified; identical bytes cannot be uploaded under a second ID.

## Release

`worker/publish.py --enable-youtube-publisher` adds exactly one binding and one SQLite class migration if absent; existing bindings, secrets, cron and routes are retained and checked. Source must match the reviewed predecessor before replacement. Production is a single api.js module with the built-in cloudflare:workers import. Preserve this class/binding on future deployments. The legacy bearer endpoints remain compatibility paths; new autonomous operations use this managed, identity-verified coordinator.

Validation covers unauthorized jobs, explicit channel mismatches, correct refresh-token selection, race/replay prevention, changed/duplicate media, old receipts, unknown upload outcomes and adoption, native schedule readback, public-state evidence and follow-up dates. Node tests replace only the Cloudflare base-class adapter; production storage/runtime is additionally checked with real read-only inspect jobs after release.

## 2026-10-25 live verification

The reviewed module was deployed through Cloudflare management after merging PR4. Source equality, all original binding metadata and the existing cron were verified; the new publisher binding is present. The public health endpoint remains HTTP 200. Both real capability jobs reached the Durable Object and refreshed the existing OAuth grants, then returned `youtube_read_403:insufficientPermissions` when reading channel identity. No video was uploaded or scheduled. This is a Google scope/permission blocker, not a missing caller-secret blocker; do not ask the owner to migrate the old shared secret again. Completing an owner-controlled YouTube connection through the already-installed Metricool publisher is the preferred next access step. The managed path remains fail-closed until authenticated identity/inventory can be verified.

If rollback is needed, retain the YouTubePublisher class, binding and durable journal and disable the new public job route. Do not deploy the old module without its new class export while the namespace binding remains, and do not delete the namespace or migration data. Future source releases must pin the actually deployed predecessor (PR4 merge 37d6977d49f66ae76a141f234eccd12fb806d562 for this source) rather than assuming a Pages deployment updated this Worker.
