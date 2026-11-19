# 源站榜单需求：稀饭动漫 Next（供本项目参考接入）

> 用户诉求记录（2026-11-19）。用途：看**当前季度热度、追番**，属于"非权威参考"，不是权威播放量。
> 本项目（bangumi-rank）已有 B 站播放量 + bgm 当季榜，本文是"再加稀饭榜单"的需求输入。

## 要接入的两个榜单

数据源站：`https://next.xifanacg.com`

| # | 榜单 | URL | 用户要的子榜 | 为什么 |
|---|---|---|---|---|
| 1 | **弹幕榜** | `?kind=danmaku_heat` | **总榜**（主）；完结榜可选 | 弹幕数反映真实观看热度；总榜第1名是"不时轻声地以俄语遮羞的邻座艾莉同学"（艾莉同学），正是用户点名要的 |
| 2 | **周热榜** | `?kind=trending_week` | **总榜/新番榜**（主） | 看最近几周热度、当前季度追番；新番榜前排是"学生会也有洞！""黑暗召唤师在地下恋爱中"等当季新番 |

## 不要的榜单

- **评分榜**（`?kind=rating`）：用户明确不要——它按 bgm 评分排，前排是 clannad / EVA 等零几年老番，对追番无用
- 飙升榜（`rising`）、宝藏榜（`hidden_gem`）：暂不接入

## 每个榜单下的子 tab

页面上有：总榜 / 新番 / 完结 / 剧场版 / 美漫。
注意：子 tab 是**页面内切换**，暂无独立 URL 参数（抓到的链接都是 `?kind=xxx#main`）——实现时需进一步确认切换机制。

## 抓取方式（已调研）

- 页面是 Next.js RSC，榜单数据**内联在 `<script type="application/ld+json">`** 的 `ItemList` 里：
  - `numberOfItems: 50`
  - 每项：`position`（名次）、`item.name`（标题）、`item.url`（含 anime id）、`item.image`（封面）、`datePublished`（年份）
  - 示例：`{"position":1,"item":{"name":"学生会也有洞！","url":"https://next.xifanacg.com/anime/3432","image":"...","datePublished":"2026"}}`
- **纯 HTTP GET + 解析 JSON-LD 即可**，不需要浏览器。适合 GitHub Action 定时抓（本项目已有每 6 小时 cron）。
- 页面标注"每 30 分钟刷新热度数据"——抓一次数据够用一段时间，不必高频。

## 注意

- 用户原话较口语："一个第1个排行榜的周榜还是总榜，第2个排行榜的周榜还是总榜还是完结榜"——
  核心意思：**两个榜单（弹幕/周热）各要总榜 + 一个新番/完结子榜**，具体组合用户会再定，先按上表记录。
- 标题关联 bgm id 可复用本项目已有的 `fetch.py` 标题清洗 + bgm 匹配逻辑。
- 建议输出为 `data.json` 的新键 `rankings.xifan_danmaku` / `rankings.xifan_weekly`，前端 `detail-tabs` 加 tab，明确标注"数据来自稀饭动漫，仅供参考"。
