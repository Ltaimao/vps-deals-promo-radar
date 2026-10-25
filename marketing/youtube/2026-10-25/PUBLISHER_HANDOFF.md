# VPSDealsWire：ChatGPT → Muse 发布交接

2026-10-25 站主指定：ChatGPT 负责内容与发布计划；Muse 负责 YouTube 查重、上传、排程、实际发布核验。站主已转述 Muse 正在等待 vw-y001 成片。禁止将 VPS 内容发到 TattooDoodle 的 Metricool 品牌 7620881。

## 当前可取片

**vw-y001：ready_for_publisher=true**。读取 [`handoffs/vw-y001.json`](handoffs/vw-y001.json) 获取全部元数据与 SHA256。成片 https://www.vpsdealswire.com/videos/vw-y001.mp4 ，约 97 秒 1080p；缩略图 https://www.vpsdealswire.com/vw-y001-thumbnail.jpg ；英文字幕 https://www.vpsdealswire.com/vw-y001.en.srt 。三个文件公开 HTTP200、字节哈希与源文件一致，浏览器也解码到 1920×1080 / 96.948667 秒。建议 2026-10-27，尚无实际 YouTube ID 或排程。其余五条素材未完成。

## 入口与分工

- 频道：@VPSDealsWire，预期 ID `UCfgVJrtBJSeViu95AnaQxyA`。发布前由 Muse 用实际账号核验。
- 内容计划：`publication-plan.json`；制作状态：`queue.json`。建议日期不是已排程。
- 完整取片包：`handoffs/<contentId>.json`；只有 `ready_for_publisher=true` 且素材公开取片验证通过，才可上传。
- ChatGPT：研究、脚本、真实录屏/原创图示、旁白、最终 MP4、缩略图、英文 SRT、标题描述/UTM、质检、计划。后续读取 Muse 回执以避免重复制作并复盘。
- Muse：频道身份与历史库存核对、上传、最终排程、隐私/受众/合成内容标签的实际判断、缩略图与字幕上传、公开发布核验与回填。
- 不互相覆盖对方记录。ChatGPT 不调用 VPS 上传/删除或创建排程；不因后续频道连接而自动接管发布。

## 首批节奏

| 内容 | 建议日期（Asia/Shanghai） | 主题 | 类型 |
|---|---|---|---|
| vw-y001 | 2026-10-27 | Shared vCPU / fair use | 横屏 |
| vw-y002 | 2026-10-30 | VPS location / latency | 横屏 |
| vw-y003 | 2026-11-01 | vCPU policy，衍生自 y001 | Short |
| vw-y004 | 2026-11-03 | NVMe vs SSD | 横屏 |
| vw-y005 | 2026-11-06 | DDoS protection terms | 横屏 |
| vw-y006 | 2026-11-08 | I/O limits，衍生自 y004 | Short |

具体小时由 Muse 根据频道情况选定并回填。不要为赶计划发布尚未交片的项目，也不要把六份脚本算作六条成片。Shorts 的描述网址不可点击；相关视频与频道外链功能须实际核验。

## 每次取片

1. 同步 main，读取包内 content ID、版本、目标频道、视频/缩略图/字幕 URL 和 SHA256。校验下载字节，不根据文件名猜素材。
2. 同时按 content ID、来源页面、标题、媒体 SHA、历史回执和实际频道库存查重；包含私享/未列出/已排程内容。调用结果不明先查实际状态，不能盲重试。
3. 说明区首行使用包内完整 UTM 链接；核验落地页仍 HTTP200。核验标题、描述、英文字幕、缩略图、非儿童受众等设置。通用合成旁白的制作事实在包内披露，不冒充真人测评。
4. 保留既有视频，不清理、删除或重发老内容。旧 Worker 403 是当时检查结果，不代表 Muse 当前使用的发布工具不可用，也不要求站主给 ChatGPT 重新授权。
5. 上传、processing、scheduled、published 分开记录。只有实际频道匹配且有真实公开视频 ID、watch URL 和公开时间，才记 published。原始回执可脱敏保存，不能提交令牌/邮箱/密钥。

## 回填约定

请在 `records/muse-<contentId>.json` 写入以下数据；不存在的值保持 null，不编造：

```json
{
  "contentId": "vw-y001",
  "publishingOwner": "muse",
  "mediaVersion": "v1",
  "mediaSha256": null,
  "verifiedChannelId": null,
  "status": "not_uploaded",
  "scheduledAt": null,
  "timezone": "Asia/Shanghai",
  "youtubeVideoId": null,
  "youtubeUrl": null,
  "actualPublishedAt": null,
  "review7At": null,
  "review28At": null,
  "checkedAt": null,
  "evidence": [],
  "error": null
}
```

实际发布时间确定后再计算 7/28 天复查日。效果看网站相关会话和互动；未验证事件与跨工具归因时，不报告逐条视频的购买/下载转化。双方通过仓库交接，不要求站主反复转发素材。
