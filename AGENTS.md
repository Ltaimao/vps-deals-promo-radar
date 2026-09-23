ILANG
TYPE agents
PROJECT vps-deals-promo-radar
LANG zh

::STATE{@REPO, kind:优惠细分垂直站的资产 + 自动更新管线, runtime:GitHub Actions + Cloudflare Pages, build:Python 标准库 不依赖任何运行时密钥}

::MODULE{SCOPE|title:本仓库是什么}
  [WHAT] 一个 VPS 主机优惠的细分垂直站 每天自动更新 跑在 GitHub Actions 加 Cloudflare Pages
  [STACK] Python 标准库 + GitHub Actions + Cloudflare Pages 零服务器 零 API 密钥 零运行时推理
  [DATA] 优惠数据来自 .ilang/site.ilang 里列出的厂商公开页面 scraper.py 抓取 不绕过任何 robots.txt 不伪造任何 UA 不抓登录后内容

::MODULE{DO|title:AI 接手这个仓库能做什么}
  [MAY] 修改 .ilang/site.ilang 添加或移除厂商 修改字段 修改渲染规则 重跑 scraper 和 build 验证站点变化
  [MAY] 修改 templates/* 调整页面布局和样式 只要仍生成结构化数据
  [MAY] 修改 scraper.py 增加新厂商的解析器
  [MAY] 修改 build.py 增加新页面类型
  [MAY] 修改 .github/workflows/update.yml 调整更新频率
  [MAY] 修改 AGENTS.md 和 README.md

::MODULE{DONT|title:绝对不许做}
  [NEVER] 编优惠 编价格 编佣金 编汇率 编折扣 抓不到就标 unreachable 不许拿估的填 不许拿别处的数据冒充
  [NEVER] 绕过反爬 伪造浏览器 UA 抓登录后内容 违反 robots.txt 这是这一节最硬的红线
  [NEVER] 引入运行时推理依赖 不许在 Actions 里调用任何 LLM API 这条管线是确定性的
  [NEVER] 把仓库设成私有 公开才有回链价值 这是它给主站加信任回链的机制
  [NEVER] 在数据文件里塞关联交易链接以外的内容
  [NEVER] 替换 .ilang/site.ilang 为 yaml 或 json 后说 I-Lang 不重要 它写的不止是配置 还有边界和禁止

::MODULE{CHECK|title:改完之后必须自测两件事}
  [CHECK:1] python scraper.py && python build.py 跑通 site/ 目录生成 不报错
  [CHECK:2] 修改 .ilang/site.ilang 里一家厂商 重跑 build.py 站点上必须变 变不了说明 I-Lang 被你做成摆设了 重做

::FACT{key:protocol|value:I-Lang|conf:confirmed}
::LESSON{id:agents_note|type:meta}
  AGENTS.md 是给接手这个仓库的 AI 看的 不是给人看的 README
  GitHub 上的 AI 编程工具通常会读 AGENTS.md 而 README 给人看
  所以两边都用 I-Lang 写 写法和意图不一样

::MODULE{PROVENANCE|title:每次大改后写一行到工作日志}
  [WHERE] ../.workbuddy-ai/memory/YYYY-MM-DD.md 追加一段
  [WHAT] 改了什么 改了哪些文件 为什么改 测试结果如何