# 每日 SEO 文章发布

> Current update — 2026-10-27: today’s release recovered through the existing workflow and publicly verified. This change extends complete reviewed future stock to **2026-10-28–2026-11-11 (15 days)** after merge. See [research and audit](seo/2026-10-27/README.md). Prior dated notes are historical; release remains08:00 Asia/Shanghai.

> Current state — 2026-10-26: today’s missed release recovered through the existing workflow and publicly verified. Complete reviewed future stock covers **2026-10-27–2026-11-10 (15 days)** after this change merges. See [research and audit](seo/2026-10-26/README.md). Prior dated notes below are historical. Release remains 08:00 Asia/Shanghai.

> **2026-10-25 更新：** 已新增 3 篇完整审阅稿与原创配图，队列延长至 **2026-11-09**；10 月 26 日至 11 月 9 日连续 15 天有完整稿件。已启用共享每日备稿巡检任务，发布一天补齐一天。下文 14 篇/11 月 6 日是原批次记录，以 [本次研究、Brief 和完整日历](seo/2026-10-25/README.md) 与 content/calendar.json 为当前依据。Windsor GSC/GA4 已实际读取；原确定性 08:00 发布流程继续使用。

按用户 2026-10-23 指令设置。时区为 **Asia/Shanghai（北京时间）**，每天 **08:00** 触发，第一次为 **2026-10-24 08:00**。

这是实际发布任务，不是聊天提醒。GitHub Actions cron `0 0 * * *` 对应 UTC 00:00；平台可能排队，部署和缓存更新也需要时间，因此不能保证页面在 08:00:00 准点可见。

## 定时触发补偿（2026-10-24 修复）

补跑时发现 Wrangler 4.152.0 要求 Node.js >=22，而原日更流程使用 Node.js 20，已导致真实部署失败。日更、代码部署和价格部署统一使用 Node.js 22 与固定 Wrangler 4.152.0。

保留 08:00 主触发，另在北京时间 08:17–23:17 每小时第 17 分钟补偿检查（UTC `17 0-15 * * *`）。GitHub 的定时事件可能延迟或丢失；这组检查减少单次触发缺失导致全天漏发的风险，但不承诺精确到分钟或平台绝对可用。

每次从 main 读取当天稿件。已提交的文章先核对正式 URL 的 200、唯一 canonical、单个 H1、可索引状态和 sitemap；全部通过则跳过构建和部署。未提交则发布当天一篇；已提交但线上核对失败则重试部署。手动 check 始终只读。跨日稿件仍不自动倒填。

## 已准备的稿件

14 篇完整英文稿覆盖 2026-10-24 至 2026-11-06；每篇至少 350 词，有首屏答案、独立搜索意图、相关内链和可读元数据。不编价格、优惠、汇率、佣金、性能或未执行的测试。目标查询是编辑选题假设，不是已获得的 GSC 搜索量。

| 北京日期 | 文章 slug | 目标查询意图 |
|---|---|---|
| 2026-10-24 | shared-vcpu-vps-fair-use | shared vCPU VPS fair use |
| 2026-10-25 | choose-vps-location-latency | how to choose VPS server location |
| 2026-10-26 | nvme-vs-ssd-vps-storage | NVMe vs SSD VPS storage limits |
| 2026-10-27 | vps-ddos-protection-checklist | VPS DDoS protection null route policy |
| 2026-10-28 | vps-email-smtp-before-buying | cheap VPS SMTP email restrictions |
| 2026-10-29 | vps-control-panel-license-costs | does VPS need paid control panel |
| 2026-10-30 | vps-order-identity-verification | VPS identity verification before purchase |
| 2026-10-31 | vps-sla-service-credits | VPS SLA service credit terms |
| 2026-11-01 | check-vps-disk-space-linux | Linux VPS disk full inodes |
| 2026-11-02 | vps-ssh-lockout-recovery | locked out of VPS SSH recovery |
| 2026-11-03 | vps-cloud-init-first-boot | VPS cloud init user data first boot |
| 2026-11-04 | persistent-vs-ephemeral-vps-storage | VPS persistent ephemeral storage rebuild delete |
| 2026-11-05 | vps-docker-log-disk-usage | Docker logs filling VPS disk retention |
| 2026-11-06 | vps-ip-reputation-checklist | VPS IP reputation assigned address checklist |

## 执行流程

1. 工作流 `.github/workflows/daily-article.yml` 从 main 读取 I-Lang 时间配置与 `content/calendar.json`。
2. 校验日期、slug、搜索意图、完整稿件、标题/描述、内链及审阅 SHA-256。
3. 08:00 前不复制稿件；到时仅复制当天一篇到 `articles/`。重复运行不生成第二篇，不覆盖已存在但不同的文件。
4. 运行测试和构建，单独提交文章，fetch/rebase 后推送，保留价格和历史更新。
5. 使用既有 CI Cloudflare 绑定部署 Pages，核对正式文章返回 200、canonical 与 sitemap。没有真实公开网址验证时，不称为发布成功。

未到期稿件留在 `content/queue/`，不会进入网站文章目录或 sitemap。仓库本身是公开的，因此稿件源文件不是保密资产。本批 14 篇均已配备原创 1200×630 PNG 主题示意图，存于 `static/articles/<slug>.png`，首段答案后展示，带说明、alt 与固定尺寸；文章列表使用同一图片作缩略图。图片只解释概念，不冒充跑分、厂商截图或实测数据。图片 SHA-256 与稿件同时审阅，缺图、图片变化、缺少 alt 或尺寸会阻止日更发布。历史文章保留原有无图兼容行为。

自日历起始日之后，build 只显示日历中已审阅、摘要相符且已到北京时间发布时刻的新稿；未排期的旧平台新文件会在日志中标记排除，避免在本站重复发布。既有历史文章 URL 保留。

日更、代码部署、价格更新共用生产发布锁，防止旧构建覆盖新构建。价格更新移至北京时间 02:20、08:20、14:20、20:20，仍为每 6 小时一次，错开文章发布窗口。平台仅保留有限待运行任务，若排队或发布失败，应检查 Actions 后补跑；不能靠 cron 配置本身认定成功。

## 核对、补跑与续稿

```bash
python3 editorial.py validate
python3 editorial.py release --dry-run
python3 editorial.py release --dry-run --at '2026-10-24T08:00:00+08:00'
# 仅核对，不发布：
gh workflow run daily-article.yml --ref main -f mode=check
# 当天已过 08:00、且明确要补跑实际发布时：
gh workflow run daily-article.yml --ref main -f mode=publish
```

`--at` 只允许与 `--dry-run` 一起使用，不能用来提前发文或伪造发布日期。已提交但部署失败的当日文章，补跑会重新构建部署，不重复写入。跨日漏发稿件需要明确调整后续日期并重新审阅，不会自动补发成多篇或倒填发布日期。

**本批结束于 11 月 6 日。** 此后没有新审阅稿件时任务会失败并显示队列不足，不调用 LLM、不生成模板凑数、不重发旧文。需要在此日期前完成下一批稿件。Actions 的失败通知遵循仓库和账号已有通知设置，未另建邮件或聊天通知服务。

新增稿件：延续连续日期，明确单一且不重复的 gap，写完整 HTML 和元数据，在 `content/calendar.json` 增加 ready 条目及准确 SHA-256；制作并审阅相应主题配图，增加 `image_sha256`（PNG 文件 SHA-256），正文使用该图片的本站路径、描述性 alt 和 `width="1200" height="630"`。发布后若实质编辑排期文章，应同时完成复核并更新对应摘要；校验失败时不能直接关闭检查。

旧交接提到另一个平台 08:49 的文章/营销任务，本环境没有其管理接口，**没有声称已停用该旧任务**。本次新增的是本站 GitHub 发布流程；未配置 YouTube、X 或外联自动推广。
