# 稀饭动漫 Next 榜单 · 站点 API / 响应文档（agent-browser 实测）

> 探索方式：2026-11-19 用 **agent-browser（Chrome 158）+ HAR 抓包 + curl 静态解析** 真实探索 `next.xifanacg.com` 得到。
> 结论先行：**榜单数据全部内联在页面 RSC（Next.js Flight）里，纯 HTTP GET 即可拿到，无需浏览器、无需登录、无需 RPC 调用。**
>  HAR 全程无 `api.xifanacg.com` JSON 请求；页面里虽有 `get_leaderboard` 等 RPC 方法名，但那是站内其它 FunCration 客户端用的，榜单不走它。

## 0. 重要修正（相对旧需求文档）

旧文档 `docs/源站榜单需求-稀饭Next.md` 写的是 `/?kind=xxx`，**实测这是错的**：
- `/?kind=danmaku_heat` 返回的是**首页**（当季新番 9 项），`kind` 参数被忽略。
- 真正的榜单页是 **`/rankings?kind=xxx`**，返回 50 项完整榜单 + 5 个子榜 sections。

旧文档说"数据在 `<script type="application/ld+json">` 的 ItemList，numberOfItems: 50"——对了一半：
- JSON-LD 的 ItemList 确实有 50 项，但**只有 `position/name/url/image/datePublished`**，没有弹幕数/播放量/评分。
- **带数值的完整数据在 RSC 数据流 `self.__next_f.push([1,"..."])` 里的 `sections`（见 §3）**，这才是要解析的主数据源。

## 1. 请求（Request）

| 项 | 值 |
|---|---|
| 方法 | `GET` |
| URL | `https://next.xifanacg.com/rankings?kind=<kind>` |
| 认证 | 无（公开） |
| 必要 Header | `User-Agent: Mozilla/5.0 ...`（curl 默认可；建议带正常 UA） |
| 返回 | `text/html; charset=utf-8`（约 540 KB，Next.js RSC 页面） |
| 刷新频率 | 页面标注"每 30 分钟刷新热度数据"；本项目 cron 每 6 小时抓一次足够 |

### kind 取值

| kind | 榜单 | 本项目是否接入 |
|---|---|---|
| `danmaku_heat` | 弹幕榜（弹幕数排序） | ✅ 接入（总榜为主） |
| `trending_week` | 周热榜（最近几周热度） | ✅ 接入（总榜/新番为主） |
| 无参数 / `/rankings` | 默认=周热榜数据 | 参考 |
| `rating` | 评分榜（按 bgm 评分，前排是 clannad/EVA 老番） | ❌ 用户明确不要 |
| `rising` | 飙升榜 | ❌ 暂不接入 |
| `hidden_gem` | 宝藏榜 | ❌ 暂不接入 |

> 子 tab（总榜/新番/完结/剧场版/美漫）是**页面内前端过滤**，无独立 URL 参数；但全部子榜数据已内联在同一页 RSC 的 `sections` 里，抓一次即可全取。

## 2. 响应结构（Response）

页面有两处数据：

### 2.1 JSON-LD（仅基础信息，可作交叉校验）

`<script type="application/ld+json">` 共 4 块：`@graph`（站点信息）、`CollectionPage`、`BreadcrumbList`、`ItemList`。
`ItemList` 的 `itemListElement` 为 50 项，每项：

```json
{
  "@type": "ListItem",
  "position": 1,
  "item": {
    "@type": "TVSeries",
    "@id": "https://next.xifanacg.com/anime/2474#primary",
    "name": "不时轻声地以俄语遮羞的邻座艾莉同学",
    "url": "https://next.xifanacg.com/anime/2474",
    "image": "https://img2.xfmanga.top/pic/cover/l/7c/8e/424883_BpzVb.jpg",
    "datePublished": "2024"
  }
}
```

### 2.2 RSC `sections`（主数据源，含全部数值）

数据在 `self.__next_f.push([1,"<flight 字符串>"])` 中。解析步骤：
1. 正则取所有 `push([1,"..."])` 的字符串片段并拼接；
2. 用 `json.loads('"' + raw + '"')` 还原转义（`\uXXXX`、中文正常）；
3. 定位 `"sections":`，做括号配对提取 JSON 数组。

`sections` 结构（弹幕榜 `danmaku_heat` 实测）：

| key | label | 条目数 | 首项 | score 含义 |
|---|---|---|---|---|
| `all` | 总榜 | 50 | 不时轻声地以俄语遮羞的邻座艾莉同学 | 弹幕数 14401 |
| `ongoing` | 新番 | 50 | 赛博朋克：边缘行者 2 | 弹幕数 77 |
| `finished` | 完结 | 50 | 不时轻声地以俄语遮羞的邻座艾莉同学 | 弹幕数 14401 |
| `movie` | 剧场版 | 50 | 电影 五等分的新娘 | 弹幕数 833 |
| `western` | 美漫 | 15 | 瑞克和莫蒂 第一季 | 弹幕数 82 |

周热榜 `trending_week`（或无参数）实测：

| key | label | 条目数 | 首项 | score 含义 |
|---|---|---|---|---|
| `all` / `ongoing` | 总榜 / 新番 | 50 | 学生会也有洞！ | 周热度 14364 |
| `finished` | 完结 | 50 | 黑色五叶草 | 7075 |
| `movie` | 剧场版 | 50 | 辉夜大小姐想让我告白-初吻不会… | 184 |
| `western` | 美漫 | 14 | 爱、死亡 & 机器人 | 214 |

## 3. Item 字段 schema（RSC sections[].items[]）

```json
{
  "id": 2474,
  "title": "不时轻声地以俄语遮羞的邻座艾莉同学",
  "titleOriginal": "時々ボソッとロシア語でデレる隣のアーリャさん",
  "coverUrl": "https://img2.xfmanga.top/pic/cover/l/7c/8e/424883_BpzVb.jpg",
  "description": "久世政近的邻座坐着一位名叫艾莉莎的女孩……",
  "director": "伊藤良太",
  "actors": ["室田雄平"],
  "metaTags": ["校园", "TV", "恋爱", "日本", "小说改"],
  "typeId": 2,
  "typeName": "完结旧番",
  "seriesId": null,
  "releaseYear": 2024,
  "releaseDate": "2024-07-03",
  "viewCount": 1163225,
  "bangumiScore": 5.5,
  "isFinished": true,
  "isRecommended": false,
  "totalEpisodes": 12,
  "currentEpisodes": 12,
  "format": "tv",
  "score": 14401,
  "rank": 1
}
```

字段说明：

| 字段 | 类型 | 说明 | 本项目用途 |
|---|---|---|---|
| `id` | int | 稀饭站番剧 id（与 bgm id 不同体系！） | 存 source_id |
| `title` | str | 中文标题 | ✅ 标题（复用 bgm 匹配） |
| `titleOriginal` | str | 日文原名 | ❌ 不显示（纯中文界面） |
| `coverUrl` | str | 封面（`img2.xfmanga.top`，非 anibt） | ✅ 封面，本地化兜底 |
| `description` | str | 简介 | 可选 |
| `metaTags` | str[] | 中文标签 | ✅ 副标题/标签行 |
| `typeName` | str | 连载新番/完结旧番/剧场版/美漫 | 区分用 |
| `releaseDate` | str | 首播日期 | 季度判断 |
| `viewCount` | int | 稀饭播放量 | ✅ 参考值（非权威） |
| `bangumiScore` | float | bgm 评分 | 可选 |
| `isFinished` | bool | 是否完结 | 完结榜用 |
| `format` | str | tv/movie 等 | 区分用 |
| `score` | int | **榜单热度值**：弹幕榜=弹幕数；周热榜=周热度 | ✅ 排序依据 |
| `rank` | int | 名次（每子榜各自 1..N） | ✅ 名次 |

## 4. 本项目接入映射

| 稀饭榜 | 本项目 rankings key | 前端 tab | 标注 |
|---|---|---|---|
| 弹幕榜·总榜 | `xifan_danmaku` | 稀饭弹幕榜 | "数据来自稀饭动漫·仅供参考" |
| 周热榜·总榜 | `xifan_weekly` | 稀饭周热榜 | 同上 |
| 周热榜·新番 | `xifan_weekly_ongoing`（可选） | 子榜 | 同上 |

- 标题关联 bgm：复用 `fetch.py` 现有 `match_bgm()` 标题清洗 + bangumi-data 目录直连 bgm id。
- 封面：`coverUrl` 是 `img2.xfmanga.top`，走本项目本地化下载兜底（不走 anibt 代理）。
- **不是权威播放量**：前端必须标注"来自稀饭动漫，仅供参考"，与 B 站真实播放量区分。

## 5. 参考：animaku 那十几个站点同理

`animaku` 系站点（与本项目同生态）接入范式相同，均可套用 §6 流程：

1. 用 agent-browser 打开站点，`network har start` → 操作页面（切榜/翻页/搜索）→ `network har stop`，看是"页面内联 RSC/JSON-LD"还是"客户端 API"。
2. 若内联（如稀饭）：curl GET + 解析即可，最省事。
3. 若客户端 API：`agent-browser network requests --filter <域>` 找 endpoint，HAR 里看 method/header/body/response，按 `derive-client` skill §3 提取 auth（cookie/bearer/x-*），生成每站一个 fetch 函数。
4. 站点 API 无版本、会变：保留 HAR 以便重新派生；加 UA/Referer；控制频率。

## 6. 可复用抓取配方（伪代码）

```python
import re, json, urllib.request

def fetch_xifan_ranking(kind, ua):
    url = f"https://next.xifanacg.com/rankings?kind={kind}"
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")

    # 取所有 RSC flight 片段并还原转义
    segs = re.findall(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', html)
    decoded = json.loads('"' + ''.join(segs) + '"')

    i = decoded.find('"sections":')
    start = decoded.find('[', i)
    depth = 0
    for j in range(start, len(decoded)):
        if decoded[j] == '[': depth += 1
        elif decoded[j] == ']':
            depth -= 1
            if depth == 0:
                end = j + 1
                break
    sections = json.loads(decoded[start:end])
    # sections: [{key,label,items:[item,...]}, ...]
    return sections
```

## 7. 验证记录

- `danmaku_heat` 总榜第 1 名 = "不时轻声地以俄语遮羞的邻座艾莉同学"（用户点名要的艾莉同学）✅
- `trending_week` 总榜第 1 名 = "学生会也有洞！"（当季新番）✅
- 5 个子榜 sections 全部提取成功，条目数 50/50/50/50/15（美漫 14~15 浮动）✅
- HAR（`/tmp/xifan-rankings.har`，30 请求）无任何 JSON API 调用，确认数据内联 ✅


## 8. 本项目实现状态（2026-11-19 已完成）

- `fetch.py` 新增 `fetch_xifan_ranking()` + `build_xifan_rank()`，`--no-xifan` 可跳过；已写入 `rankings.xifan_danmaku` / `xifan_weekly` / `xifan_weekly_ongoing`。
- 前端 detail-tabs 与首页胶囊末尾新增「稀饭弹幕榜 / 稀饭周热榜 / 稀饭新番」三个 tab，卡片与详情显示「X 热度」并标注「数据来自稀饭动漫，仅供参考」。
- 稀饭封面（`img2.xfmanga.top`，直连极慢 8s+）**不使用其域名**。因稀饭封面与 bgm 封面同构（同一 `pic/cover` hash 路径），在数据层 `build_xifan_rank()` 把域名改写为 `https://bgmimg.anibt.net/`（bgm/anibt 域名），实测全部加载成功。

## 9. 探索结论（用户原话完整记录）

> 用户 2026-11-19 原话（agent-browser 探索 + HAR 抓包后的完整结论，逐字保留，供后续复刻/交接）：
>
> 「用 agent-browser（Chrome 158）+ HAR 抓包 + curl 实测发现：
> - 需求文档写的 `/?kind=xxx` 是错的（返回首页 9 项），真正榜单页是 `/rankings?kind=xxx`
> - HAR 全程无 JSON API 调用；数据全部内联在页面 RSC Flight 的 sections 里，纯 HTTP GET 即可，无需浏览器/登录/RPC
> - 5 个子榜（总榜/新番/完结/剧场版/美漫）数据都在同一页，子 tab 切换是纯前端过滤
> - 字段比文档记录的更全（含弹幕数/播放量/bgm评分等）
>
> 完整 API 文档 docs/源站榜单-稀饭Next-API文档.md（201 行）：请求方法/URL/kind 取值/响应结构/Item 字段 schema/接入映射/可复用抓取配方/验证记录，并写了"animaku 十几个站点同理"的接入范式。
>
> 抓取实现 fetch.py：fetch_xifan_ranking() + build_xifan_rank()，--no-xifan 开关，标题复用现有 bgm 匹配。
>
> 前端接入：三个 tab（稀饭弹幕榜/周热榜/新番），显示"X 热度"+"数据来自稀饭动漫，仅供参考"。
>
> 验证：弹幕榜第1名 = 不时轻声地以俄语遮羞的邻座艾莉同学（你点名要的）；周热榜第1名 = 学生会也有洞！；封面彩色显示、热度值、来源标注全部正确，截图确认。
>
> 另外恢复了一个被清掉的 scripts/config.json（容器重启丢失），并重起了 8899 静态服务。」

> 补充更正（用户后续明确指出）：**只取稀饭的播放量数据，图片一律用 bgm 的 anibt 域名，不用稀饭的图片域名。** 已据此改为数据层域名改写（见 §8），截图复核通过。

## 10. 迭代更新日志机制（每段时间写入一次）

本项目要求：**每隔一段时间（每次探索/改动/验证告一段落）就把结论追加到本文档的「迭代更新日志」**，便于后续会话无缝接手。

### 迭代更新日志

| 时间 | 类型 | 内容摘要 |
|---|---|---|
| 2026-11-19 | 探索 | agent-browser + HAR 实测稀饭 Next：纠正 URL 为 `/rankings?kind=`，确认数据内联 RSC sections、无 JSON API，提取完整字段 schema |
| 2026-11-19 | 实现 | `fetch.py` 新增稀饭抓取 + `build_xifan_rank()`，写入 3 个 rankings key；前端新增 3 个 tab + 来源标注 |
| 2026-11-19 | 修正 | 封面改用 bgm/anibt 域名（同构 hash 改写），去掉稀饭 `img2.xfmanga.top` 域名；弹幕榜/周热榜/新番 50/50/50 封面全部加载成功 |
| 2026-11-19 | 环境 | 重建容器重启丢失的 `scripts/config.json`；重启 8899 静态服务 |
| 2026-11-19 | 修正 | 用户纠正：稀饭弹幕/周热榜不放首页顶部，改为首页只留「稀饭动漫」入口（标题+↗外链角标+入口条），内容移到详情页 tabs |
| 2026-11-19 | 新增 | 数据源外链角标模式：首页标题旁与详情标题旁加 ↗ 跳原网站；`SOURCE_TABS` 定义各站 URL，后续网站照此追加 |
| 2026-11-19 | 凭据 | 用户提供 Map9876 全仓库权限 GitHub PAT；记忆与 README 记录其存在/用途（明文不落盘、私密仓库不泄露），用于推送本项目到 github.io |
| 2026-11-19 | 部署 | 本项目已推送至 `Map9876/anime-popular-rank`（main，commit 00ee1d2）；workflow 改用 GitHub 官方 Pages Actions（configure/upload/deploy）+ enablement；PAT 无 Pages 管理权限，需在 GitHub 网页手动启用一次 Pages（Source=GitHub Actions） |

> 写入规则：每次告一段落，在上表追加一行（时间/类型/摘要）；重要原话或纠正写入 §9 或对应章节。
