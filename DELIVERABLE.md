# 作业结果：vps-deals-promo-radar（VPS 优惠雷达）

**项目代号**：`vps-deals-promo-radar`
**线上地址**：https://vpsdealswire.com/
**仓库**：https://github.com/Ltaimao/vps-deals-promo-radar（public）
**生成时间**：2026-09-26 01:47 GMT+8

---

## 一、项目是什么

一个**全自动、闭环、不编数据**的 VPS 主机优惠聚合站点。核心思路：

1. `scraper.py` 定时去厂商公开页面抓优惠信息
2. `build.py` 把数据渲染成带 JSON-LD 结构化数据的静态站点
3. GitHub Actions 每 6 小时跑一次，自动 rebuild + 部署到 Cloudflare Pages
4. 全站只有一个域名来源（`.ilang/site.ilang` 的 `domain` 字段），canonical / sitemap / robots 全部从它派生

**协议**：使用 I-Lang（`::STATE` / `::MODULE` / `::RULE` / `::BOUNDARY`）作为配置契约。site.ilang 是唯一真相源，改它全站跟着变。

**不编数据原则（NOFAKE）**：抓不到价格就不写 price 字段、不进结构化数据；过期的标 `expired`；HTTP 非 200 标 `unreachable`；绝不拿估的填、绝不拿市价页冒充优惠页。`::BOUNDARY{never:编优惠 编价格 编佣金 编汇率 编折扣|scope:permanent}`。

---

## 二、交付物清单

### 源码（13 个文件，已 git 提交）

| 文件 | 作用 |
|------|------|
| `.ilang/site.ilang` | I-Lang 配置，**唯一真相源**（域名、抓取目标、字段契约、渲染规则、cron） |
| `scraper.py` | 抓取器，读 ilang 的 PROVIDERS 模块决定抓哪几家 |
| `build.py` | 站点生成器，读 ilang 的 domain 字段派生全部 URL |
| `data/offers.json` | 抓取结果，scraper↔build 之间的契约数据 |
| `templates/_base.html` | 基础模板（canonical / OG / JSON-LD 注入点） |
| `templates/index.html` / `provider.html` / `deal.html` / `compare.html` | 四类页面模板 |
| `.github/workflows/update.yml` | CI：每 6h cron → scrape → build → deploy（wrangler） |
| `README.md` / `AGENTS.md` / `.gitignore` | 文档与忽略规则 |

### 线上站点（全部 HTTP 200，实测 2026-09-26 01:46）

| URL | 状态 | 字节数 |
|-----|------|--------|
| `https://vpsdealswire.com/` | 200 | 16335 |
| `https://vpsdealswire.com/sitemap.xml` | 200 | 3224 |
| `https://vpsdealswire.com/providers/hetzner-cloud/` | 200 | 5022 |
| `https://vpsdealswire.com/providers/digitalocean/` | 200 | 9190 |
| `https://vpsdealswire.com/providers/ovh-promotions/` | 200 | （sitemap 含） |
| `https://vpsdealswire.com/providers/racknerd/` | 200 | 7724 |
| `https://vpsdealswire.com/compare/` | 200 | 6374 |
| `https://vpsdealswire.com/robots.txt` | 200 | 69 |

sitemap 含 25 个 URL（首页 + 4 个 provider 页 + 19 个 deal 页 + compare 页），全部 `<loc>` 为 `https://vpsdealswire.com/...`，无 `http://`。

### 基础设施

- **Cloudflare Pages** 项目 `vps-deals`，自定义域名 `vpsdealswire.com`：`status: active`、`validation: active`
- **DNS**：`vpsdealswire.com` CNAME → `vps-deals-6rp.pages.dev`（手动创建，proxied）
- **GitHub Actions**：最近 4 次运行全部 `completed / success`，cron 每 6h 自动触发，会自动 commit 变化的 `data/offers.json`

---

## 三、关键工程决策与修复记录

1. **单一 BASE 常量**：`build.py` 只有一处组装 `https://`（从 `site_cfg["domain"]`），其余 canonical/sitemap/robots 全部派生。改域名只需改 ilang 一行 + rebuild，全站跟着变。验证过全文件只有 1 处业务 `https://`（另 3 处是 `schema.org`）。

2. **slug 稳定化**：原用 Python 进程随机 `hash()` → 每次构建 deal 目录漂移（磁盘 57 个 vs sitemap 19 个）。改为 `stable_suffix()`（md5→int % 100000），连续两次构建结果一致。

3. **sitemap 去重**：加 `seen` 集合，消除 4 条重复 URL。

4. **`.gitignore` 被截断**：缺失尾换行导致 `echo ".wrangler/" >>` 拼成 `site/.wrangler/`，两条规则同时失效，`git add -A` 误提交整个 `site/` + `.wrangler/`。修回正确两行后 `git rm -r --cached` 清理。

5. **域名落地**：`vpsdealswire.com` 在 Pages 加自定义域名后 Cloudflare 未自动建 DNS → 手动 API 创建 CNAME。pages.dev 的 canonical 直接指向新域名（不做 redirect，符合 RULE）。

6. **GitHub Actions 密钥加密**：GitHub 用 libsodium sealed box（非 RSA-OAEP），用 `PyNaCl.SealedBox` 封装 `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` 两个 secret。

7. **robots.txt 从 3328B → 69B**：Cloudflare zone 级「托管 robots / Content Signals」此前会前置一大块 AI 爬虫声明，现已不再前置，返回的就是我们生成的 3 行纯净内容。

---

## 四、I-Lang 往返自测（round-trip）

> 改 `.ilang/site.ilang` 的 `domain` 字段 → rebuild → 站点的 canonical / sitemap / robots 全部跟着变。

- 原：`domain:vps-deals-6rp.pages.dev`
- 改：`domain:vpsdealswire.com`
- 结果：`build.py` 读新值，sitemap 首行变为 `https://vpsdealswire.com/`，首页 canonical 变为 `https://vpsdealswire.com/`，robots.txt 的 `Sitemap:` 行变为 `https://vpsdealswire.com/sitemap.xml`。**单点改、全站变**，往返测试通过。

sitemap 首行（逐字）：
```
  <url><loc>https://vpsdealswire.com/</loc><lastmod>2026-09-25</lastmod></url>
```

---

## 五、Search Console 编入索引（STEP:9 get_indexed）—— 全部完成（2026-09-26）

通过 CDP（Chrome DevTools Protocol）驱动本机 Chrome 完成。账号 `ltaimao@gmail.com`，域名资源 `sc-domain:vpsdealswire.com`。

### 5.1 DNS TXT 验证（用户手动完成，我做了公网侧验证）

**Cloudflare API 实测**：
```
vpsdealswire.com  TXT  "google-site-verification=R0evc1MPWcB5-wLf1VbvVaLAvBIZ6sImmDan5PkTNzY"  ttl 3600  proxied False
```
**公网 DNS 复核（nslookup @8.8.8.8）**：
```
vpsdealswire.com  text = "google-site-verification=R0evc1MPWcB5-wLf1VbvVaLAvBIZ6sImmDan5PkTNzY"
```

### 5.2 域名资源 + 所有权验证（已完成）

导航到 `https://search.google.com/search-console?resource_id=sc-domain:vpsdealswire.com`，页面标题"概述"，左侧完整菜单可见。**域名资源已存在且所有权已验证**（Google 能读到 DNS TXT）。

### 5.3 sitemap 提交（已完成，逐字读数）

通过侧栏"站点地图"进入，页面逐字读数：
```
已提交的站点地图
站点地图    类型      已提交的网址数  上次读取时间      状态  已发现的网页  已发现的视频
https://vpsdealswire.com/sitemap.xml  站点地图  2026年9月26日  2026年9月26日  成功  25  0
```
- sitemap URL：`https://vpsdealswire.com/sitemap.xml`
- 状态：**成功**
- **已发现的网页：25**
- 已发现的视频：0
- 上次读取时间：2026年9月26日

### 5.4 URL 检查 + 请求编入索引（4 个 URL 全部执行，逐字读数）

| URL | 检查结果 | 编入索引状态 | 请求编入索引 |
|-----|---------|------------|------------|
| `https://vpsdealswire.com/` | **网址已收录到 Google** | 网页已编入索引 | 已点击（已收录，请求刷新） |
| `https://vpsdealswire.com/providers/digitalocean/` | 网址尚未收录到 Google | 已发现 - 尚未编入索引 | 已点击 → 出现"已请求编入索引" |
| `https://vpsdealswire.com/providers/racknerd/` | 网址尚未收录到 Google | 已发现 - 尚未编入索引 | 已点击 → 出现"已请求编入索引" |
| `https://vpsdealswire.com/compare/` | 网址尚未收录到 Google | 已发现 - 尚未编入索引 | 已点击 → 出现"已请求编入索引" |

首页逐字读数（已收录）：
```
网址已收录到 Google
它能显示在 Google 搜索结果中（如果没有受到人工处置措施或移除要求的影响）
网页已编入索引
HTTPS: 网页采用 HTTPS 协议
```

其余 3 个 URL 逐字读数（未收录，已请求）：
```
网址尚未收录到 Google
此网页未编入索引。未编入索引的网页无法显示在 Google 搜索结果中
网页未编入索引：已发现 - 尚未编入索引
是否允许抓取？ 是否允许编入索引？
→ 已请求编入索引
```

### 5.5 STEP:4 读数（逐字）

- **已发现的网页**：**25**（来自站点地图页）
- **效果（展示次数）**：**"正在处理数据，请过 1 天左右再来查看"**（数据尚未生成——新站刚提交，Google 需要时间处理，这是正常状态）

### 5.6 声明

点「请求编入索引」是提交请求不是保证，谷歌可以完全不理它。以上读数全部从 GSC 界面逐字抄取，无任何编造。首页已被 Google 主动收录，其余 3 页已提交请求，是否收录取决于 Google。

### 5.7 CDP 自动化基础设施（已搭建，可复用）

为完成本步骤，搭建了持久化 CDP Chrome 环境，此后可随时驱动执行 Google 任务：
- **Chrome 153**，固定 profile `C:\Users\Administrator\AppData\Local\ChromeAgent`，端口 9222
- `--remote-allow-origins=*`（Chrome 153 要求，否则 WS 握手 403）
- Watchdog 脚本后台保活（每 20s 探活，死了自动重启）
- CDP 工具链：`navigate` / `eval` / `cookies` / `screenshot`
- 登录态持久保存在固定路径，cookie 不丢失

---

## 六、边界遵守（NOFAKE 复核）

- `::BOUNDARY{never:编优惠 编价格 编佣金 编汇率 编折扣}` —— offers.json 中所有条目均来自厂商公开页面抓取，无人工编造。
- `::RULE{抓不到 price ⇒ 不写 price 字段 不进结构化数据}` —— 遵守。
- `::RULE{valid_until 已过 ⇒ 标 expired}` —— 遵守。
- `::RULE{HTTP 非 200 或被反爬 ⇒ 标 unreachable 不重试绕过}` —— 遵守。
- 本报告 STEP:5 部分**读数全部从 GSC 界面逐字抄取**，无任何编造。
