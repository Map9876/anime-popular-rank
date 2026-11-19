# 番剧排行榜（anime-popular-rank）

> 仓库定位：github action 爬取 B站一些上传动漫的UP主的番剧播放量以及一些网站（稀饭动漫等）的番剧榜单；后续还会接入 linetv / kktv / 巴哈姆特等榜单。

## 静态页 + GitHub Action

**在线地址（GitHub Pages）**：https://map9876.github.io/anime-popular-rank/

独立、纯静态的番剧排行榜页面。由 GitHub Action 定时抓取公开数据并生成 `data/data.json`，前端读取 JSON 渲染。页面可被 animaku 直接 iframe 嵌入。

## GitHub 仓库与凭据说明

- 本仓库 `Map9876/anime-popular-rank` 用于部署到 GitHub Pages（公开仓库，Pages 所需）。
- 推送使用一个由用户提供的 **GitHub Personal Access Token**，属于账号 **Map9876**，具有该账号所有仓库权限，可创建/推送仓库。
- **安全约定**：token 明文**不写入本 README 或任何会推送的文件**（公开仓库会被扫描泄露）。需要推送时从会话上下文或环境变量取，用完即弃，不落盘。
- 用户需要新建仓库时，按项目语义自动取合适名称并推送；推送前扫描项目内敏感信息（key/token/credentials），确认无泄漏再推。

## 数据源（全部免登录、公开）

| 数据 | 来源 | 说明 |
|---|---|---|
| B 站 UP 主投稿播放量 | `api.bilibili.com/x/space/wbi/arc/search` | WBI 签名，`vlist.play` 即播放量；默认 UID `690151424`（KAYGEZ）。`config.json` 的 `ups` 数组支持多位 UP |
| 标题清洗 → bgm id | `bgmapi.anibt.net/v0/search/subjects` | 清洗 `第N话`/`【】`/技术标记后搜索 bgm，相似度阈值匹配，带缓存 |
| bgm 当季番剧 | 同上，`filter.air_date` 按季度 | 季度算法与 Animaku 一致（当前年 + 季度首月），`sort=heat` |
| 稀饭弹幕榜/周热榜 | `GET https://next.xifanacg.com/rankings?kind=<kind>` | 页面内联 RSC，纯 GET 解析 `sections`；**仅供参考**。完整请求/响应文档见 `docs/源站榜单-稀饭Next-API文档.md` |
| 全量番剧目录（bgm id） | `bangumi-data/bangumi-data` 的 `data/items/{年}/{月}.json` | 只拉当季 3 个月份文件（<200KB），用中文译名直连 bgm id；**不做 53MB submodule** |
| bgm 封面 | `bgmimg.anibt.net` | Animaku 同款国内代理，替代 `lain.bgm.tv`，防止图片失效 |
| B 站封面 | 下载到 `assets/covers/` | 本地兜底，原链接失效时自动回退 |

参考实现来自 `kylinholmes/BangumiFans` 的 `tool/collect_up_catalog.py`（WBI 签名）与 `uerax/Animaku` 的 `packages/shared/src/bangumi-endpoint.ts`（anibt 代理）。参考架构来自 `Map9876/wnacg-manga-rank`（GitHub Action 定时抓取 → commit 数据 → 部署 Pages）。

## 排名口径

| 季度 | 排序指标 | 说明 |
|---|---|---|
| 当前季度 | `累计播放量 ÷ 距首集投稿天数` | 不做贝叶斯平均，直接反映播放速率 |
| 过往季度 | 贝叶斯平滑后的播放速率 | 老番增长慢、样本稀疏，向全站速率中位数收敛，避免失真 |

- **播放量累加**：同一作品的所有投稿（单集、重投、合集）播放量全部相加；稿件被删除后仍保留在 `data/videos.json` 缓存中并继续计入。
- **首集投稿时间**：取该作品所有投稿中最早的 `published`；重复投稿不会重置起算时间。
- 页面季度行右侧「统计口径」按钮点击后弹出轻量 Popover 说明上述口径（纯 CSS 实现，不引入 UI 库）。

## 目录

```
bangumi-rank/
├── .github/workflows/update.yml   # 定时抓取 + 部署 Pages
├── scripts/
│   ├── config.json                # UP 主、API host、限流参数
│   └── fetch.py                   # 抓取 + 清洗 + 匹配 + 聚合
├── data/
│   ├── data.json                  # 前端唯一入口
│   ├── history/<season>.json      # 每季度快照，累积保留
│   ├── bgm-match-cache.json       # 标题→bgm 匹配缓存
│   └── cache/                     # 原始响应缓存（失败保留上次成功）
├── assets/covers/                 # 本地封面兜底
├── index.html / style.css / app.js
├── docs/UI交互设计规格.md         # 零依赖交互组件的精确 Token 与复刻手册
└── README.md
```

## 本地运行

```bash
cd /workspace/bangumi-rank
python3 scripts/fetch.py                 # 抓全量（首次可能触发 B 站风控，脚本自动退避重试）
python3 scripts/fetch.py --bgm-only      # 只抓 bgm 当季（B 站风控时验证页面用）
python3 -m http.server 8899             # 浏览 http://localhost:8899
```

常用测试参数：`--max-pages 2` 限制 B 站页数、`--match-recent 6` 限制 bgm 匹配条数、`--no-localize` 不下载封面、`--refresh` 忽略缓存。

## 部署

把本目录作为独立 GitHub 仓库推送。`update.yml` 已配置：

- `schedule` 每 6 小时（UTC）自动运行；`workflow_dispatch` 支持手动触发
- 抓完数据后 commit 回仓库（`[skip ci]` 避免循环触发）
- 再用 `peaceiris/actions-gh-pages` 把静态文件部署到 `gh-pages` 分支

无需任何 Python 第三方依赖（仅用标准库）。

## iframe 嵌入 animaku

页面使用 hash 路由（`#/rank/up`），所有内部跳转都在 iframe 内完成，不会顶破父页面。嵌入示例：

```html
<iframe src="https://<你的GitHub用户名>.github.io/<仓库名>/"
        style="width:100%;height:100dvh;border:0" title="番剧排行榜"></iframe>
```

前端已实现：
- **纯中文界面**：不显示日文原名；卡片副标题与详情简介均用中文 bgm 标签（季度/制作/题材）替代
- **数据源外链角标**：每个外部数据源（稀饭动漫等）在首页区块标题旁、详情标题旁都有 ↗ 角标可跳原网站；新增站点在 `SOURCE_TABS` 追加 `{key,label,url}` 即可，后续网站同理
- **无底部导航**：删除 B 站式底部导航栏，内容占满视口
- **紧凑自适应**：尺寸用 `clamp()+vw` 随屏宽缩放（非固定 px），一屏约 4 组榜单；每榜只渲染前 20 条 + `content-visibility`，避免几百张图卡顿
- **软页面**：卡片点击 → hash 切换 view，不刷新；`history.back()` 回退也不刷新
- **视口预加载**：`IntersectionObserver` 监听横向滑动卡片，进入视口即预生成详情 HTML，点击秒开
- **季度筛选**：按 `meta.seasons` 过滤（不显示「全部」）；当前季度默认
- **详情滚动折叠**：上滑时 banner 与榜单 tabs 随之滚出，顶部出现居中的小「热门榜单」矩形标题
- **图片防失效**：bgm 封面走 anibt 代理，B 站封面 57 张全部本地化到 `assets/covers/`，`onerror` 双兜底
- **不展示虚构内容**：只渲染真实抓取的 B 站播放量与 bgm 当季番剧，没有玄幻榜/古风榜等虚构榜单，也没有虚拟用户名

## 数据契约

`data/data.json`：

```jsonc
{
  "meta": { "generated_at", "current_season", "seasons", "ups", "total_videos", "matched_videos", "sources" },
  "rankings": {
    "up": [
      { "rank", "title", "title_original", "bvid", "bvids", "views", "episodes", "season",
        "first_published", "days_since_first", "play_rate", "score", "prior_rate",
        "bgm_id", "bgm_cover", "bgm_score", "tags", "summary", "cover", "local_cover" }
    ],
    "bgm_season": [ { "rank", "title", "title_original", "bgm_id", "cover", "score", "air_date", "summary", "tags", "season" } ]
  }
}
```

`up` 榜按 bgm 作品聚合播放量（同一部番的多话合并），`bgm_season` 是 bgm 当季热度榜。

## 后续扩展点

- **多位 UP 主**：在 `scripts/config.json` 的 `ups` 数组追加 `{mid, name}`，`fetch.py` 已遍历合并
- **第三方播放量页（Animaku 内置十几个站点）**：作为「非权威参考」，建议新增独立榜单键（如 `rankings.third_party`），在 `detail-tabs` 加一个 tab，并明确标注来源
- **linetv / kktv 排行榜**：同上，作为独立数据源接入；建议保留 `history/<season>.json` 快照做趋势对比
- 新数据源统一输出到 `data.json` 的 `rankings` 下，前端 `detail-tabs` 加对应 `data-tab` 即可

## 已知限制

- B 站对未登录接口有风控（HTTP 412 / 业务 -352），脚本会退避重试并复用缓存；在 GitHub Actions 干净出口 IP 上通常可抓全量
目录里只拉当季的 4/5/6 或 10/11/12 月文件（`fetch_bangumi_catalog()`），提取 bgm id + 中日文标题 + 放送时间，存 `data/bangumi-catalog.json`（当季 84 部仅 17KB）。匹配标题时**优先用目录自带的 bgm id 直接绑定**（中文译名更贴近 B 站标题），命中后按 id 从 bgm API 补封面/评分/标签。实测 12 条标题中 10 条由目录直连命中。Animaku 本身没用 bangumi-data，它只调 bgm API + 一份本地 id 映射快照。
- 当前只抓最新 80 条投稿做 bgm 匹配，避免过多请求；历史季度数据靠 `history/` 累积
>>>>>>> f6d008a (feat: 番剧排行榜静态页（B站播放量/bgm当季/稀饭动漫榜单 + GitHub Action 定时抓取）)
