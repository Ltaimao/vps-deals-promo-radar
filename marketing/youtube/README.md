# YouTube 网站推广运营

> 2026-10-26：现有三条内容保持原状；下一条 vw-y004（建议11月3日）已实际制作与质检，待本次部署后核验公开素材。此时尚未新增排程/交付就绪。详见 2026-10-25/production/vw-y004；以最新 records 为最终状态。

> 当前交接：Muse 已回填 vw-y001 的实际视频 `QXW-Ty9ECZY` 与 2026-10-25 13:00:33 北京时间发布记录，禁止重复上传。其自定义缩略图/字幕尚未附加，见 [Muse 回执](records/muse-vw-y001.json)。vw-y002（10月30日）与 vw-y003（11月1日）为已部署并完成公开 URL/哈希核验的新成片，两个交付包均可供 Muse 发布。状态以 [发布交接](2026-10-25/PUBLISHER_HANDOFF.md) 和各 handoff 文件为准。日期为建议；本方不操作 VPS YouTube 发布。


> **站主最新分工 — 2026-10-25：VPS 的 YouTube 实际发布由 Muse 负责。** ChatGPT 负责内容制作与发布计划：选题、脚本、成片、缩略图、标题描述、引流链接、质检和交付包；不创建 VPS 的 YouTube/Metricool 排程、不上传/删除视频，也不因连接出现而自动启用发布。纹身站仍由本方完整运营。请优先阅读 [发布交接](2026-10-25/PUBLISHER_HANDOFF.md) 和 [建议发布计划](2026-10-25/publication-plan.json)。下方为接手时通用/历史方案，不能覆盖这项最新分工。

> 以下为历史发布器检查记录，不是要求站主再次授权；VPS 发布现由 Muse 执行。

> 2026-10-25 publisher update: managed API code is deployed; original bindings, routes and cron retained. Actual channel reads for both grants fail with Google `403 insufficientPermissions`. No upload was attempted. The old local shared secret is no longer required. See `2026-10-25/publisher-verification.json`.

Owner mandate: autonomously operate the two channels to promote the websites. The two uploaded handovers are evidence and historical preferences, not a binding instruction to retain their production or upload methods. No new video is claimed published by this takeover.

## Outcome and initial experiment

Qualified site visits and useful site actions are the primary outcome. Views, watch time, impressions CTR and subscriber growth are diagnostic metrics, not the business goal. Start with a two-week experiment: **two practical horizontal videos and one derivative Short per channel per week**, changing cadence if production quality, actual demand or available data warrants it. Avoid an automatic one-article/one-video rule. Do not catch up by mass uploading an old backlog.

Tattoo Doodle: real lettering comparisons, exact-word proofreading and reference-card/artist handoffs. VPS Deals Wire: plan fit, documented limits and buying decisions, with actual dated sources when a price is necessary. A provider's policy label is not an executed benchmark. Historical unsupported claims such as guaranteed tattoo outcomes or “tested & ranked” require verification before reuse. Do not delete or re-upload historical videos to correct their titles.

Each long-form video answers one concrete question, shows a genuine example and offers one relevant next step. Target roughly 90–180 seconds when the demonstration supports it; do not stretch a weak script to a fixed duration. Use real screen recording and exports, original explanatory graphics, restrained small labels, good narration and optional closed captions. No caption wall, generated product interface, fabricated result or single zooming image for an entire video. Titles should earn attention with a clear problem and demonstrated answer; numbers, fear, a year or performance claims are not mandatory decoration.

Shorts are discovery content. YouTube's [official link documentation](https://support.google.com/youtube/answer/13748639?hl=en) says URLs in Shorts descriptions/comments are non-clickable and external clickable links in long-form descriptions require advanced-feature access. Prefer a related full video, then its targeted website link; [related-video setup](https://support.google.com/youtube/answer/14075157?hl=en) also needs advanced features. These channel features and editor/API support are not yet verified, so no related link or clickable external link is claimed configured. A profile website link is another route once access is available.

## Attribution and review

Use `utm_source=youtube`, `utm_medium=organic_video`, the site-specific campaign and a stable content ID. Links go to the exact live guide or tool. The profile link gets a separate content ID and cannot reliably attribute visits to one Short. When a Short leads to a long video, the final description link identifies that long video's content; do not assign its downloads back to a Short without evidence.

Read GA4 source/medium and landing-page sessions/engaged sessions. Only report tool use, reference-card downloads or provider outbound actions after the actual event names and instrumentation have been verified. Cross-tool identity is not established; YouTube views and GA4 sessions are not a person-level conversion funnel. Use 7- and 28-day windows from the real publication time, allow reporting delay and retain small-sample uncertainty. The first two weeks establish a baseline, not a promised numeric growth target.

## Historical state at takeover — 2026-10-25

- Repository dual-token routing is present in `worker/api.js`. Both channel refresh-token secret **names** exist in the deployed Worker; presence does not prove validity, scopes or channel identity. Secret values were neither read nor copied.
- The former missing-caller-credential problem was removed on 2026-10-25: a managed capability-job publisher is implemented, merged and deployed without exporting old secrets. However, actual authenticated inspections on both channels returned `403 insufficientPermissions` at the Google channel/inventory API. **Automatic publishing remains blocked by Google read/identity permissions.** Metricool still has Pinterest only; no YouTube account is connected in Windsor. The earlier request to migrate the old caller credential is obsolete; the remaining action is owner-completed YouTube authorization, preferably via the already-connected Metricool publisher. Do not request or paste secrets in chat.
- The legacy uploader defaults non-`tattoo` channel strings to VPS; new autonomous operations use the managed publisher documented in the VPS repository at `worker/YOUTUBE_PUBLISHER.md`. It requires an explicit channel, confirmed actual YouTube channel ID, current inventory reconciliation, per-channel durable content/file/slug reservations and an attempt journal. The managed path has been tested, but its current real inspections fail closed on Google permissions. Do not call upload to discover which channel the token targets, and do not use an already-published video as a test.
- Cloudflare KV returned **54 historical upload receipts**, including repeated slugs and test entries. They are upload-event evidence only; the records omit channel identity and public/private/deleted state. They are not a list of 54 currently public videos. No record, video or test clip was deleted.
- Public YouTube channel reads were throttled, and direct oEmbed requests were rejected by the execution network. Current public inventory, channel-level performance, advanced-feature access and valid OAuth scopes remain unverified. Do not circumvent this by spoofing a browser identity or pretend the handover is a current API read.
- Windsor GA4 query window 2026-09-25–2026-10-22, dimensions session_source_medium/landing_page_plus_query_string, metrics sessions/engaged_sessions, filter source-medium contains youtube: both properties returned a completed empty report. This is no matching reported data in this window/filter, not proof of zero historical attribution or zero video value.

## Publication gates and safe recovery

1. Read main, the channel config, current inventory and prior attempts. Preserve the existing Pinterest/SEO tasks, videos, production secrets and subscription/price services.
2. Verify an authenticated read of the actual channel ID and current uploads. The handover's expected IDs are provisional until confirmed. Never rely solely on a token variable name, a handle or an upload response containing an ID.
3. Confirm the exact source page is live, facts and prices are current, media rights and correct domain are checked, full and mobile-size visual/audio review passes, and the final video is actually encoded. Script approval is not video approval.
4. Use a stable `contentId` plus channel, source slug, file SHA-256 and attempt record to check for duplicates. Distinct source slugs alone do not prove distinct content. Keep derivatives separately identified. Compare server receipts with the current YouTube upload list, including private/unlisted material available to the owner.
5. After a real upload, query the video's actual channel, title, privacy, processing state and URL. Mark published only after its public status and expected ownership are verified. Keep uploading/processing/unverified distinct. An ambiguous timeout means reconcile first, not blindly retry tomorrow.
6. No old-video deletion, wrong-channel bulk cleanup, OAuth-consent click or credential rotation is authorized by a pasted handover. User authorization covers routine new production/marketing work, not copying secret values into documents. If owner authentication is required, explain the exact one-time requirement.

## Production stock and reporting

`2026-10-25/queue.json` contains 12 fully written scripts across both sites (six for this site, four horizontal plus two Shorts), each with a title, thumbnail concept, storyboard, landing page and UTM. The proposed dates are editorial targets, **not actual scheduled posts**. State is script_reviewed/media_pending/access_unverified. Do not count these as finished video inventory or scheduled YouTube uploads. Prepare the first long video per site before scaling the full batch; retain at most one week's completed-media stock initially while testing the creative direction.

Routine reporting: meaningful published results, failed publication, wrong channel, authorization changes or a depleted usable stock. Give a short weekly summary of published links, qualified traffic and the next creative decision. No daily vanity-metric report and no unsupported conversion promises.


