# 滚动 15 天 SEO 备稿与发布巡检

执行日期：2026-10-25；时区：Asia/Shanghai。用户已确认 GAS 指 GSC + GA4，并授权准备未来稿、每日发布与补充。本批只新增稿件和排期，不替换历史文章或图片，不改 Pinterest 排期。**2026-10-26 至 2026-11-09 连续 15 天每天一篇完整审阅稿**；今天及历史日期不计入未来库存。

## 研究口径

- Windsor GSC：2026-09-25 至 2026-10-22，query/page 维度；另比对 10-16 至 10-22 与 10-09 至 10-15 的 query 维度。排除最近三天以减轻延迟影响，不保证所有历史数据最终不变。查询行求和不是网站总量。
- Windsor GA4：相同 28 天，landing_page_plus_query_string、session_source_medium、session_default_channel_group、sessions、engaged_sessions。全渠道与 Organic Search 分开读；渠道名按 GA4 返回值保留，不能仅用 medium 字符串重分类。未核验下载事件与查询转化归因，不报告每篇下载转化。
- GSC Wizard 的专用机会分析返回订阅到期，已停止重试，通过 Windsor 取得真实数据，未购买套餐。
- 外部趋势：实际搜索并读取竞争页面和官方资料。未取得可复核的 Google Trends 时间序列或关键词月搜索量；“2026 趋势”营销文、社交帖子与黑五季节性只作定性线索，不称为量化热搜。每篇目标 query 是待验证编辑假设。
- 新内容选择独立任务意图，而不是对同一个头部词拆分同义词页面。已有主页面进入复查清单，不批量新建重复价格/字体/Stencil 页面。

## 执行和验收

本目录 briefs.json 保留新增文章主词、辅助词、问题、大纲、独立价值、来源、CTA、配图方案及计划复查日；calendar.json 列出全部未来 15 天。完整正文和配图位于发布队列，不以标题或 brief 充数。

新图为原创程序教学图，以真实 DejaVu 字体排版，不是 AI 生成文字、产品截图或真实纹身成果。字体许可已核对系统 fonts-dejavu-core/copyright，未分发字体文件。图示只解释该篇决策，正文明确适用边界。全尺寸代表图和全部缩略图已目视检查，程序校验尺寸、解码、文件与正文对应。内审图像评分 88/100（主题准确 28/30、构图 21/25、文字清晰 18/20、品牌 11/15、权利 10/10）；这是内部主观质检，不代表点击效果。源脚本为 source/render_diagrams.py。

既有 GitHub Actions 08:00 日更继续负责到期发布；平台 cron 可能延迟，不承诺秒级可用。新建且仅新建一个共享任务“两站 SEO 备稿与巡检”：北京时间上午约 09:00 执行（弹性窗口），先查当天真实公开 URL，再补齐之后连续 15 天；发布一天补一天，质检失败不入 ready 库存。不得在 Actions 内增加运行时 LLM，也不提前发布未来正文。新稿通过 PR 检查后合并，保留 main 上并发价格与运营记录。当前任务定义见 automation.json。

每次复查公开 URL 的 HTTP 200、canonical、单个 H1、可索引状态、sitemap 与图片；部署任务成功本身不等于发布成功。稿件的计划 +7/+28 天日期仅供排期，真实复盘按实际发布时间重算。低样本不作因果或转化优胜结论；日常报告异常和有意义结果，每周简短汇总。

## VPS 站研究结论

7 天 GSC 查询展示较前 7 天：vps cost 4→28、vps price 7→28、vps hosting price 2→18、vps deals 4→19。它们是本站报表中的增长，不能说成全网趋势或确定转化机会。保留现有成本/比较/黑五落地页作为承接，不新增多个同义价格排行。含引号和排除站点等明显搜索操作符的厂商查询从选题优先级中排除。

GA4 全渠道首页 153 sessions；Organic Search 中首页 bing / organic 为 6 sessions，renewal-prices 页面 google / organic 为 1 session、1 engaged session。不能将全渠道首页流量当自然流量，也不能从一条文章会话认定题材已胜出。提前准备黑五购买后的退出、恢复、切换流程，是季节性编辑判断，不声称已获得相应关键词流量。新增 3 篇与原有 12 篇未来稿合并，滚动库存补齐到 11 月 9 日。

竞品/官方观察（2026-10-25 访问）：[Bluehost 黑五页](https://www.bluehost.com/blog/vps-black-friday/)把焦点放在购买与长期成本；其活动文案不作为本站价格证据，不照抄优惠。取消稿对照 [EuroVPS](https://www.eurovps.com/faq/how-can-i-cancel-my-services/)与[TransIP](https://www.transip.eu/knowledgebase/386-how-do-i-cancel-service)的官方流程，确认不同提供方存在不同通知条件；正文不把某一家期限套给全部厂商。

恢复稿比较 [Rested](https://restedbackups.com/blog/vps-backup-restore-test-checklist)与[AgentXCloud](https://agentxcloud.com/blog/can-you-test-a-vps-snapshot-before-restoring-production)的应用恢复任务，使用 [DigitalOcean](https://docs.digitalocean.com/products/snapshots/how-to/create-and-restore-droplets/)核验具体恢复约束。本文区分购买是否含备份与实际恢复验收，不声称做过一次真实灾难演练。DNS 稿对照 [DCHost](https://docs.dchost.com/en/docs/guides/server-migration/)与[Virtarix](https://virtarix.com/blog/technical-guides/dns-change-planning-checklist-vps/)，以 [Cloudflare TTL 文档](https://developers.cloudflare.com/dns/manage-dns-records/reference/ttl/)核验缓存规则；强调回退不合并新写入，避免固定等待时间保证。

待复查而未擅自改写：历史 WordPress 迁移文章存在固定 TTL/等待期及“无停机”措辞，需要按具体配置收紧；现有续费、Windows VPS 和黑五页面先核验时效再优化。现有源文件/URL保持。
