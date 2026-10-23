# VPS Deals Wire — 当前环境交接

核对日期：2026-10-23（北京时间）。本文件区分代码事实、历史交接记录和未核实事项，不把旧交接里的“standing 授权”视为新的对外操作指令。

## 已核实的事实

- 仓库 `/workspace/vps-deals-promo-radar`，GitHub `Ltaimao/vps-deals-promo-radar`；主站规范地址 `https://www.vpsdealswire.com/`，裸域跳转 www。
- Python 3.12 + 标准库构建，无 LLM API。配置事实源为 `.ilang/site.ilang`，文章源为 `articles/*.html`。
- 2026-10-23 全站改版提交 `7d9e4bf` 已部署并逐页验证。不要把该记录理解为以后每次修改都已部署。
- 当前提交的数据快照：2026-10-23T02:25:28Z，32 家厂商、222 条原始提取记录、28 篇文章。这是历史快照，不是实时在线套餐数。用 `data/offers.json` 的时间戳和实际结果更新数字。
- 日更使用 `daily-article.yml`，北京时间每日 08:00 触发；首批日期和补跑流程见 [日更说明](DAILY_EDITORIAL.md)。GitHub Actions `update.yml` 每 6 小时（北京时间 02:20/08:20/14:20/20:20）计划抓取、构建并提交数据；`deploy.yml` 在 main 推送时构建并部署 Pages。两条流程均应先运行回归测试。
- 本环境使用平台注入的 HTTPS Git 认证，普通 `git fetch` / `git push origin HEAD:main` 已实测可用；旧 `ghpush` 和 `/opt/hatch/...` 依赖在本环境不存在。
- 主站订阅由独立 Worker 提供；仓库代码发信走 Resend，秘密绑定名 `RESEND_API_KEY`。Pages 部署不等于 Worker 部署，也不证明发信成功。
- GA4 衡量 ID 只从 I-Lang ANALYTICS 读取。`affiliate_click` 表示联盟出口点击；`alert_request_accepted` 表示 API 接受请求，不能当作确认订阅、订单或收入。

## 本地验证

```bash
cd /workspace/vps-deals-promo-radar
python3 -m unittest discover -s tests -v
node --test tests/test_worker.mjs  # Node 20+; no real emails or external API calls
python3 scraper.py --output /tmp/vps-offers-check.json
python3 build.py --data /tmp/vps-offers-check.json --output /tmp/vps-fresh-site --preserve-history
python3 build.py --preserve-history
python3 preview_server.py 8788
```

- 默认开发使用已提交数据；在线抓取是独立检查，其输出放在仓库外。不要提交验证时新生成的 `data/history.json`。
- 抓取使用真实声明的 bot UA，先检查 robots.txt；规则拒绝或不可读取就停止该来源。每个 HTTP 重定向目的地也必须通过检查。404/410 的 robots 文件视为未声明限制。没有浏览器 UA 回退、反爬绕过或登录抓取。
- 提取金额必须有紧邻的明确计费周期；信用额度、附近其他商品的月付文案、按 GB 存储单价都不能冒充 VPS 月租。历史记录没有周期时显示“period unverified”，不补造。
- 原始货币保持不变，不使用写死汇率排名。机器接口中的 USD 月付字段仅用于明确为 USD/month 的记录，其他记录保留原价与币种，USD 字段为空。
- `refetch_empty.py` 已改用同一 robots 检查客户端，不依赖 CDP。旧 `refetch.json` 缺少当前抓取策略或快照标记时不再并入构建。
- I-Lang 的 provider 清单决定已有数据中哪些厂商可以渲染及其来源；新增厂商必须先真实抓取，不能仅填配置就生成价格。
- 网站本地预览不模拟线上 Worker/KV、真实邮件投递或 Cloudflare middleware。

## 发布与回滚

1. `git status --short`，保护已有文件；`git fetch origin main`。
2. 只提交本次源代码、文档和测试；不提交调试数据、凭据、构建目录、验证快照。
3. rebase 到 `origin/main` 后重跑测试与构建；不得覆盖 Actions 推进的数据和历史。
4. 明确授权部署后，`git push origin HEAD:main`，等待该 SHA 对应的 Actions 部署成功。
5. 在正式域名核对首页、厂商页、指南、隐私/方法论、样式、sitemap 和真实 404。不要把工作流排队或仅 push 成功称为上线。
6. 回滚源代码使用新的 revert 提交并重新部署；不要 force-push 或回滚后来产生的真实价格历史。
7. Worker 是独立发布单元；部署前核对线上源码与所有绑定，不要沿用旧凭据辅助程序覆盖线上 secrets/路由。

## 联盟及内容规则

- 追踪 URL 只从 I-Lang AFFILIATE 读取，不拼接、不替换 PID、不把凭据写进仓库。
- 首页 Sponsored 名单由 RENDER.homepage_sponsored 控制，目前 3 张。厂商 Official site 仅在匹配联盟配置时使用追踪 URL，并就近披露。
- 隐私页的厂商/网络名单与按钮使用同一匹配逻辑生成；来源链接保持非联盟裸链。
- 不虚构性能测试、公司、用户规模、佣金、优惠、汇率或销量。正文历史价格必须注明来源日期，不冒充实时推荐。
- 不删除现有文章 URL、图片或视频。标题/描述精简不改 slug、不伪造更新日期。
- 没有付费广告、购买链接、自动外联或批量申请授权。业务操作以用户当前指令为准。

## 尚未核实，不能照抄为当前成果

| 项目 | 所需证据 / 下一步 |
|---|---|
| 旧环境 daily article、X、早报等 cron | 原平台任务列表、近 7 天运行结果；本仓库 Actions 不涵盖这些任务 |
| GSC 的 1 click / 350 impressions、已收录 17 等 | 对应 property 最新 28 天和前 28 天导出；原值只作为旧文档历史陈述 |
| GA4 实际流量及事件入库 | GA4 Realtime/DebugView 与后续报表；页面脚本存在不证明后台收到了事件 |
| 联盟“10 家已获批、5 家待审”与佣金 | 网络后台审批、协议和结算报表；代码只证明配置了这些链接，不证明审批或收入 |
| 邮件投递、MX、订阅转化 | Worker 健康检查不等于真实邮件送达；仅在获准测试地址下做完整确认/退订测试 |
| 旧审计、Secure Vault 与 `~/.x-oauth/` 路径 | 原平台资产；本环境未验证存在或可用，不复制、索取或输出秘密值 |
| 推广帖、YouTube 上传、外联回音 | 公开链接与对应后台记录；不可仅根据交接宣称成功 |

## Worker 修复与发布

Worker 补丁为新请求/重发的 pending 邮箱和 token 添加同样的 30 天 TTL；确认后的有效订阅不继承 pending TTL。成功读取数据后的定时任务会清理可证实超过 30 天的旧 pending 记录及对应 token，不删除 active 或缺失日期的记录。缺失日期记录需要留存复核，不能猜日期或批量删除。

提醒只比较同币种且明确月付的历史，并要求不同快照确认。未标周期的历史不冒充月付价格基线。使用 Node 模拟测试验证，不向真实用户发送测试邮件。

当前聊天未暴露 Cloudflare 连接器工具，但仓库既有 CI Cloudflare 凭据已通过只读核对，可以复用而无需读取或复制秘密值。受保护发布流程仅在手动触发时执行：

```bash
gh workflow run worker-maintenance.yml --ref main -f operation=inspect
# 只读核对成功后，已获授权的发布可执行：
gh workflow run worker-maintenance.yml --ref main -f operation=deploy
```

worker/publish.py 要求线上单模块源码匹配明确的上一版或目标版，未知源码拒绝覆盖。使用与 Wrangler 相同的 keep_bindings 元数据保留所有绑定类型，不复制或输出秘密值。只写脚本端点，不修改路由或定时触发器；发布后重读并核对源码、绑定元数据和 schedules。后续 Worker 改动必须把 workflow 的 --expected-ref 更新为已核实的线上前置版本，不能跳过 guard。旧 worker/deploy.py 已停用。

RESEND_API_KEY、OAuth、YouTube/X 等原有绑定必须在发布前后保留。发布或健康检查不证明邮件送达、GA4 事件入库或联盟订单成立。
