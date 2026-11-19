#!/usr/bin/env python3
"""
静态番剧排行榜数据生成器。

数据源（全部公开、免登录）：
  1. B 站 UP 主投稿：/x/space/wbi/arc/search（WBI 签名，vlist.play 即播放量）
  2. bgm.tv：bgmapi.anibt.net 的 /v0/search/subjects（当季番剧 + 标题匹配 bgm id）
  3. bgm 封面走 bgmimg.anibt.net 代理，B 站封面本地化兜底，避免链接失效。

产出：
  data/data.json               前端唯一入口（含全部季度榜单）
  data/history/<season>.json   每季度快照，累积保留
  data/cache/**                原始响应缓存，重跑复用
  assets/covers/<bvid>.jpg     本地封面兜底
"""
import argparse
import gzip
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = DATA / "cache"
HISTORY = DATA / "history"
COVERS = ROOT / "assets" / "covers"
CONFIG = json.loads((ROOT / "scripts" / "config.json").read_text(encoding="utf-8"))

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36")
WBI_MIXIN = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
             27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13]


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def current_season(dt=None):
    """Animaku 同款：当前年份 + 当前季度首月。返回 2026Q4 与 air_date 起点。"""
    dt = dt or datetime.now(timezone.utc)
    first = ((dt.month - 1) // 3) * 3 + 1
    q = (dt.month - 1) // 3 + 1
    return f"{dt.year}Q{q}", f"{dt.year}-{first:02d}-01"


def season_of(date_str):
    """YYYY-MM-DD -> YYYYQN；无效返回 None。"""
    if not date_str or len(str(date_str)) < 7:
        return None
    s = str(date_str)[:10]
    try:
        y, m = int(s[:4]), int(s[5:7])
    except ValueError:
        return None
    if not 1 <= m <= 12:
        return None
    return f"{y}Q{(m - 1) // 3 + 1}"


def load(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def cached_get(cache_key, fetcher, refresh=False):
    """带落盘缓存的请求；失败时保留上一次成功结果。"""
    path = CACHE / (cache_key + ".json")
    prior = load(path)
    if prior and not refresh:
        return prior["body"] if "body" in prior else prior
    try:
        body = fetcher()
        save(path, {"url": body.get("_url", ""), "fetched_at": now_iso(), "body": body})
        return body
    except Exception as exc:  # noqa: BLE001 - 网络失败保留旧缓存是本脚本的设计
        print(f"  [warn] {cache_key}: {type(exc).__name__}: {exc}", flush=True)
        return (prior or {}).get("body")


BANGUMI_DATA_RAW = ("https://raw.githubusercontent.com/bangumi-data/"
                    "bangumi-data/master/data/items")


def season_months(season):
    """2026Q4 -> [(2026,10),(2026,11),(2026,12)]"""
    try:
        year, q = season.split("Q")
        y, qi = int(year), int(q)
    except (ValueError, AttributeError):
        return []
    return [(y, m) for m in range((qi - 1) * 3 + 1, qi * 3 + 1)]


def fetch_bangumi_catalog(season, refresh=False):
    """从 bangumi-data 拉当季全量番剧目录（按月份文件，每个仅几 KB~百 KB）。

    只取 bgm id / 中日文标题 / 放送时间 / 类型，不引整个 53MB 仓库做 submodule。
    """
    out = []
    for year, month in season_months(season):
        url = f"{BANGUMI_DATA_RAW}/{year}/{month:02d}.json"

        def fetch_url():
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    return {"_data": json.loads(resp.read())}
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    return {"_data": []}  # 尚未开放的未来月份
                raise

        payload = cached_get(f"bangumi-data-{year}-{month:02d}", fetch_url, refresh)
        rows = (payload or {}).get("_data") or []
        for item in rows if isinstance(rows, list) else []:
            bgm_id = None
            for site in item.get("sites") or []:
                if site.get("site") in ("bangumi", "anibt") and site.get("id"):
                    try:
                        bgm_id = int(site["id"])
                    except (ValueError, TypeError):
                        pass
                    break
            if not bgm_id:
                continue
            zh = ((item.get("titleTranslate") or {}).get("zh-Hans") or [])
            out.append({
                "bgm_id": bgm_id,
                "title": item.get("title", ""),
                "title_cn": zh[0] if zh else "",
                "begin": item.get("begin", ""),
                "type": item.get("type", ""),
            })
    # 按 bgm_id 去重
    seen, unique = set(), []
    for row in out:
        if row["bgm_id"] not in seen:
            seen.add(row["bgm_id"])
            unique.append(row)
    return unique


def fetch_xifan_ranking(kind, refresh=False):
    """抓稀饭动漫 Next 榜单。数据内联在页面 RSC Flight 的 sections 里，纯 GET 即可。

    见 docs/源站榜单-稀饭Next-API文档.md。返回 {kind, sections:[{key,label,items}]}。
    """
    url = f"https://next.xifanacg.com/rankings?kind={kind}"

    def fetch_url():
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as resp:
            html = resp.read().decode("utf-8", "replace")
        segs = re.findall(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', html)
        if not segs:
            raise ValueError("no RSC flight payload in page")
        decoded = json.loads('"' + ''.join(segs) + '"')
        i = decoded.find('"sections":')
        if i < 0:
            raise ValueError("no sections in RSC payload")
        start = decoded.find('[', i)
        depth = 0
        end = None
        for j in range(start, len(decoded)):
            if decoded[j] == '[':
                depth += 1
            elif decoded[j] == ']':
                depth -= 1
                if depth == 0:
                    end = j + 1
                    break
        if end is None:
            raise ValueError("unbalanced sections array")
        sections = json.loads(decoded[start:end])
        return {"kind": kind, "_url": url, "sections": sections}

    return cached_get(f"xifan-{kind}", fetch_url, refresh)


def build_xifan_rank(payload, section_key, bgm_client, match_cache, catalog, match_fn, localize=True):
    """把一个稀饭 section 转成前端 ranking 条目；标题复用现有 bgm 匹配。

    score=榜单热度值（弹幕榜=弹幕数，周热榜=周热度），viewCount=稀饭播放量（非权威）。
    """
    out = []
    for sec in (payload or {}).get("sections", []):
        if sec.get("key") != section_key:
            continue
        for it in sec.get("items", []):
            title = (it.get("title") or "").strip()
            # 优先用已有标题缓存（不发新请求）；缓存未命中且 bgm_client 可用时才走完整匹配
            cached = match_cache.get(title)
            if cached is not None:
                match = cached
            elif match_fn and bgm_client is not None:
                match = match_fn(title, bgm_client, match_cache, catalog)
            else:
                match = None
            # 封面只用 bgm 图源（anibt 域名），不使用稀饭的图片域名（用户要求）
            bgm_cover = (match or {}).get("bgm_cover") or ""
            if not bgm_cover and it.get("coverUrl"):
                # 稀饭封面与 bgm 封面同构（同一 hash 路径），改写域名为 anibt 即为 bgm 图源
                bgm_cover = it["coverUrl"].replace("https://img2.xfmanga.top/", "https://bgmimg.anibt.net/") \
                                         .replace("http://img2.xfmanga.top/", "https://bgmimg.anibt.net/")
            out.append({
                "rank": it.get("rank"),
                "title": (match or {}).get("bgm_name_cn") or title,
                "title_original": "",  # 纯中文界面，不展示日文原名
                "source_id": it.get("id"),
                "source": "xifan",
                "score": it.get("score"),          # 榜单热度值
                "views": it.get("viewCount"),      # 稀饭播放量（参考）
                "bangumi_score": it.get("bangumiScore"),
                "tags": (it.get("metaTags") or [])[:4],
                "cover": "",                       # 不存稀饭域名图片
                "local_cover": "",
                "bgm_id": (match or {}).get("bgm_id"),
                "bgm_cover": bgm_cover,
                "release_date": it.get("releaseDate"),
                "is_finished": it.get("isFinished"),
                "note": "数据来自稀饭动漫，仅供参考",
            })
    return out


class BiliClient:
    def __init__(self, gap):
        self.gap = gap
        self.last = 0.0
        self.mixin = None

    def _throttle(self):
        wait = self.gap - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()

    def raw(self, endpoint, params, throttle=True, retries=5):
        url = CONFIG["bili"]["api"] + endpoint + "?" + urllib.parse.urlencode(params)
        headers = {
            "User-Agent": UA,
            "Referer": "https://space.bilibili.com/690151424/video",
            "Origin": "https://space.bilibili.com",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        last_exc = None
        for attempt in range(retries):
            if throttle:
                self._throttle()
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    body = resp.read(12_000_001)
                    if len(body) > 12_000_000:
                        raise ValueError("oversized_response")
                    if body.startswith(b"\x1f\x8b"):
                        body = gzip.decompress(body)
                data = json.loads(body)
            except urllib.error.HTTPError as exc:
                last_exc = exc
                if exc.code in (412, 429) and attempt < retries - 1:
                    delay = [5, 10, 20, 40, 80][min(attempt, 4)]
                    print(f"  [warn] HTTP {exc.code}, retry in {delay}s "
                          f"({attempt + 1}/{retries})", flush=True)
                    time.sleep(delay)
                    continue
                raise
            code = data.get("code")
            # 未登录访问 /nav 会返回 -101，但 wbi_img 仍然可用，这是 WBI 签名的正常路径
            if endpoint.endswith("/nav") and (data.get("data") or {}).get("wbi_img"):
                return data
            if code not in (0, None):
                if code == -352 and attempt < retries - 1:
                    delay = [5, 10, 20, 40, 80][min(attempt, 4)]
                    print(f"  [warn] API -352 风控, retry in {delay}s "
                          f"({attempt + 1}/{retries})", flush=True)
                    time.sleep(delay)
                    continue
                raise ValueError(f"api_code_{code}: {data.get('message')}")
            return data
        raise last_exc or RuntimeError("raw failed")

    def sign_mixin(self):
        if self.mixin:
            return self.mixin
        nav = self.raw("/x/web-interface/nav", {})
        imgs = nav["data"]["wbi_img"]
        text = "".join(
            Path(urllib.parse.urlparse(imgs[k]).path).stem for k in ("img_url", "sub_url"))
        if len(text) < 64:
            raise ValueError("bad_wbi_img")
        self.mixin = "".join(text[i] for i in WBI_MIXIN)
        return self.mixin

    def arc_search(self, mid, page, refresh=False):
        def fetch():
            mixin = self.sign_mixin()
            # 先节流再取时间戳并签名，确保 wts 与请求发出时刻一致
            self._throttle()
            params = {
                "mid": mid, "pn": page, "ps": CONFIG["bili"]["page_size"],
                "order": "pubdate", "tid": 0, "platform": "web",
                "web_location": "333.1387", "order_avoided": "true",
                "dm_img_list": "[]", "dm_img_str": "V2ViR0wgMS4w",
                "dm_cover_img_str": "QU5HTEUgKEFwcGxlLCBBcHBsZSBHUFUp",
                "dm_img_inter": '{"ds":[],"wh":[0,0,0],"of":[0,0,0]}',
                "wts": str(int(time.time())),
            }
            clean = {k: re.sub(r"[!'()*]", "", str(v)) for k, v in params.items()}
            params["w_rid"] = hashlib.md5(
                (urllib.parse.urlencode(sorted(clean.items()), quote_via=urllib.parse.quote)
                 + mixin).encode()).hexdigest()
            data = self.raw("/x/space/wbi/arc/search", params, throttle=False)
            data["_url"] = "bili://arc/" + str(mid) + "/" + str(page)
            return data
        return cached_get(f"bili-arc-{mid}-{page}", fetch, refresh)


class BgmClient:
    def __init__(self, gap):
        self.gap = gap
        self.last = 0.0

    def _throttle(self):
        wait = self.gap - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()

    def call(self, endpoint, payload=None, refresh=False, key=None):
        cache_key = key or ("bgm-" + digest([endpoint, payload]))
        path = CACHE / (cache_key + ".json")
        prior = load(path)
        if prior and not refresh:
            return prior["body"]

        def fetch():
            self._throttle()
            url = CONFIG["bgm"]["api"] + endpoint
            if payload is None:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
            else:
                req = urllib.request.Request(
                    url, data=json.dumps(payload).encode("utf-8"),
                    headers={"User-Agent": UA, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
            data["_url"] = url
            return data

        try:
            body = fetch()
            save(path, {"url": body.get("_url", ""), "fetched_at": now_iso(), "body": body})
            return body
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] bgm {endpoint}: {type(exc).__name__}: {exc}", flush=True)
            return (prior or {}).get("body")

    def season_subjects(self, air_from, air_to, limit=None):
        limit = limit or CONFIG["bgm"]["season_limit"]
        out, offset = [], 0
        while len(out) < limit:
            body = {
                "keyword": "", "sort": "heat",
                "filter": {"type": [2], "air_date": [f">={air_from}", f"<{air_to}"]},
                "nsfw": False,
            }
            data = self.call(f"/v0/search/subjects?limit=50&offset={offset}", body,
                             key=f"bgm-season-{air_from}-{air_to}-{offset}")
            rows = data.get("data") or []
            out.extend(rows)
            total = data.get("total") or 0
            page_size = data.get("limit") or len(rows)
            if len(rows) < page_size or offset + len(rows) >= total:
                break
            offset += len(rows)
        return out[:limit]

    def search(self, keyword):
        body = {"keyword": keyword, "filter": {"type": [2]}, "nsfw": False}
        data = self.call("/v0/search/subjects?limit=10&offset=0", body,
                         key="bgm-search-" + digest(keyword))
        return (data or {}).get("data") or []


# --------------------------------------------------------------------------
# 标题清洗
# --------------------------------------------------------------------------
TITLE_BRACKETS = re.compile(r"『([^』]{2,})』|《([^》]{2,})》")
TITLE_NOISE = [
    re.compile(r"第\s*\d+\s*[-~～至—]?\s*\d*\s*[话話集期]"),
    re.compile(r"(?:全|更新至?|全)\s*\d+\s*[话話集期]"),
    re.compile(r"[【\[（(][^】\]）)]{0,40}[】\]）)]"),
    re.compile(r"(?:1080[Pp]|2160[Pp]|4[Kk]|720[Pp]|蓝光|高清|超清|中字|中日|双语|字幕组|熟肉|周更|日更|完结|合集|剧场版|OVA|OAD|特番|预告|PV|CM)"),
    re.compile(r"[✅✨🔥💥❤️♥★☆]+"),
]


def clean_title(raw):
    """从 B 站投稿标题里提取番名主标题。"""
    title = (raw or "").strip()
    m = TITLE_BRACKETS.search(title)
    if m:
        title = next(g for g in m.groups() if g)
    for pattern in TITLE_NOISE:
        title = pattern.sub(" ", title)
    title = re.sub(r"\s+", " ", title).strip(" \t-_|·:：,，。.!！?？~～")
    return title


def similarity(a, b):
    a, b = (a or "").strip().lower(), (b or "").strip().lower()
    if not a or not b:
        return 0.0
    base = SequenceMatcher(None, a, b).ratio()
    if a in b or b in a:
        base = max(base, 0.93)
    # 中文标题包含关系：较短者长度 / 较长者长度
    if len(a) >= 4 and len(b) >= 4:
        overlap = len(set(a) & set(b)) / max(len(set(a) | set(b)), 1)
        base = max(base, overlap * 0.82)
    return base


def match_bgm(title, client, cache, catalog=None):
    """标题 -> bgm 作品。优先用 bangumi-data 目录自带的 bgm id 直接绑定，
    再回退 bgm 搜索。命中目录后按 id 拉详情补封面/评分/标签。"""
    if not title:
        return None
    if title in cache:
        return cache[title]

    best = None
    best_score = 0.0
    from_catalog = False

    # 1) bangumi-data 目录：中文译名/原名直接对标题，命中即锁定该 bgm id
    if catalog:
        for item in catalog:
            score = max(similarity(title, item.get("title_cn")),
                        similarity(title, item.get("title")))
            if score > best_score:
                best, best_score, from_catalog = item, score, True

    # 2) 目录没命中再用 bgm 搜索
    if not from_catalog or best_score < CONFIG["bgm"]["match_min_score"]:
        for row in client.search(title):
            score = max(similarity(title, row.get("name_cn")),
                        similarity(title, row.get("name")))
            if score > best_score:
                best, best_score, from_catalog = row, score, False

    result = None
    if best and best_score >= CONFIG["bgm"]["match_min_score"]:
        bgm_id = best.get("id") or best.get("bgm_id")
        # 按 id 取权威详情（封面/评分/标签/air_date）；目录命中时尤其需要
        detail = {}
        if bgm_id:
            payload = client.call(f"/v0/subjects/{bgm_id}", None,
                                  key=f"bgm-subject-{bgm_id}")
            detail = payload or {}
        host = CONFIG["bgm"]["image_host"]
        images = detail.get("images") or {}
        cover = images.get("large") or images.get("common") or ""
        if "/pic/" in cover:
            cover = re.sub(r"^https?://[^/]+", "https://" + host, cover)
        result = {
            "bgm_id": bgm_id,
            "bgm_name": detail.get("name") or best.get("name") or best.get("title", ""),
            "bgm_name_cn": detail.get("name_cn") or best.get("name_cn") or best.get("title_cn") or "",
            "bgm_cover": cover,
            "bgm_air_date": detail.get("date") or best.get("air_date") or best.get("begin"),
            "bgm_score": ((detail.get("rating") or {}).get("score")),
            "bgm_tags": (detail.get("tags") or [])[:5],
            "match_score": round(best_score, 3),
            "match_source": "bangumi-data" if from_catalog else "bgm-search",
        }
    cache[title] = result
    return result


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def fetch_up_videos(client, mid, refresh=False):
    videos, total = {}, None
    for page in range(1, CONFIG["bili"]["max_pages"] + 1):
        data = client.arc_search(mid, page, refresh)
        if not data:
            break
        payload = data.get("data") or {}
        rows = (payload.get("list") or {}).get("vlist") or []
        total = (payload.get("page") or {}).get("count", total)
        for row in rows:
            bvid = row.get("bvid")
            if not bvid:
                continue
            videos[bvid] = {
                "bvid": bvid,
                "aid": row.get("aid"),
                "raw_title": row.get("title", ""),
                "title": clean_title(row.get("title", "")),
                "cover": (row.get("pic") or "").replace("http://", "https://"),
                "author": row.get("author"),
                "mid": str(row.get("mid", mid)),
                "views": int(row.get("play") or 0),
                "published": row.get("created"),
                "length": row.get("length"),
                "description": row.get("description", ""),
            }
        print(f"  page {page}: +{len(rows)} videos (total declared {total})", flush=True)
        if not rows or (total and page * CONFIG["bili"]["page_size"] >= total):
            break
    return list(videos.values()), total


def localize_cover(bvid, url):
    """下载 B 站封面做本地兜底；失败返回空串。"""
    if not url:
        return ""
    path = COVERS / f"{bvid}.jpg"
    if path.exists() and path.stat().st_size > 1024:
        return f"assets/covers/{path.name}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            blob = resp.read(5_000_000)
        if len(blob) < 1024:
            return ""
        path.write_bytes(blob)
        return f"assets/covers/{path.name}"
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] cover {bvid}: {type(exc).__name__}", flush=True)
        return ""


def build_rank(videos, bgm_matches, season_items, current_season):
    """按 bgm 作品聚合播放量；同一部番的所有投稿（含重投/合集合稿）全部累加。

    排名口径：
      当前季度 = 累计播放量 / 距首集投稿天数（不做贝叶斯）
      过往季度 = 对播放速率做贝叶斯平滑（增长慢、样本稀疏，避免失真）
    """
    groups = {}
    for v in videos:
        match = bgm_matches.get(v["title"])
        key = f"bgm:{match['bgm_id']}" if match else f"raw:{v['title']}"
        g = groups.setdefault(key, {
            "title": (match or {}).get("bgm_name_cn") or v["title"],
            "title_original": (match or {}).get("bgm_name") or "",
            "bgm_id": (match or {}).get("bgm_id"),
            "bgm_cover": (match or {}).get("bgm_cover") or "",
            "bgm_score": (match or {}).get("bgm_score"),
            "bgm_air_date": (match or {}).get("bgm_air_date"),
            "tags": (match or {}).get("bgm_tags") or [],
            "summary": v.get("description", ""),
            "videos": [], "views": 0,
        })
        g["videos"].append(v)
        g["views"] += v["views"]  # 重投/合集与单集全部累加

    today = datetime.now(timezone.utc)
    for g in groups.values():
        # 首集投稿时间 = 该作品所有投稿中最早的时间（被删除的稿件仍在缓存里）
        pubs = [v["published"] for v in g["videos"] if v["published"]]
        first = min(pubs) if pubs else None
        g["first_published"] = first
        days = max((today - datetime.fromtimestamp(first, timezone.utc)).days, 1) if first else 1
        g["days_since_first"] = days
        g["play_rate"] = round(g["views"] / days, 2)
        latest = max(g["videos"], key=lambda x: x["published"] or 0)
        g["bvid"] = latest["bvid"]
        g["cover"] = latest["cover"]
        g["published"] = latest["published"]
        g["raw_title"] = latest["raw_title"]
        g["episodes"] = len(g["videos"])
        g["latest_ep_title"] = latest["title"]
        first_date = datetime.fromtimestamp(first, timezone.utc).strftime("%Y-%m-%d") if first else None
        g["season"] = season_of(g["bgm_air_date"]) or season_of(first_date)
        g["bvids"] = [v["bvid"] for v in g["videos"]]
        g.pop("videos", None)

    # 贝叶斯先验：全站播放速率中位数，比均值更稳健
    rates = sorted(g["play_rate"] for g in groups.values())
    prior_rate = rates[len(rates) // 2] if rates else 0.0
    prior_strength = 500  # 等效播放量
    for g in groups.values():
        if g["season"] == current_season:
            g["score"] = g["play_rate"]  # 当前季度：直接 播放量/首集投稿天数
        else:
            w = g["views"] / (g["views"] + prior_strength)
            g["score"] = round(w * g["play_rate"] + (1 - w) * prior_rate, 2)
        g["prior_rate"] = prior_rate

    # bgm 当季番剧（真实来源：bgm 热度榜）
    season_rank = []
    for i, s in enumerate(season_items, 1):
        images = s.get("images") or {}
        cover = images.get("large") or images.get("common") or ""
        if "/pic/" in cover:
            cover = re.sub(r"^https?://[^/]+", "https://" + CONFIG["bgm"]["image_host"], cover)
        season_rank.append({
            "rank": i,
            "title": s.get("name_cn") or s.get("name"),
            "title_original": s.get("name"),
            "bgm_id": s.get("id"),
            "cover": cover,
            "score": (s.get("rating") or {}).get("score"),
            "air_date": s.get("air_date"),
            "summary": s.get("summary", ""),
            "tags": (s.get("tags") or [])[:4],
        })

    up_rank = sorted(groups.values(), key=lambda x: -x["score"])
    for i, item in enumerate(up_rank, 1):
        item["rank"] = i
    return up_rank, season_rank


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="忽略缓存，重新请求")
    ap.add_argument("--no-localize", action="store_true", help="不下载本地封面")
    ap.add_argument("--no-xifan", action="store_true", help="跳过稀饭动漫榜单抓取")
    ap.add_argument("--max-pages", type=int, default=None, help="限制抓取页数（测试用）")
    ap.add_argument("--match-recent", type=int, default=None, help="限制 bgm 匹配条数（测试用）")
    ap.add_argument("--bgm-only", action="store_true", help="只抓 bgm 当季榜，跳过 B 站（风控时验证页面用）")
    args = ap.parse_args()
    if args.bgm_only:
        CONFIG["ups"] = []
        CONFIG["bili"]["match_recent"] = 0
    if args.max_pages:
        CONFIG["bili"]["max_pages"] = args.max_pages
    if args.match_recent:
        CONFIG["bili"]["match_recent"] = args.match_recent

    season, air_from = current_season()
    q = int(season.split("Q")[1])
    air_to = f"{int(season[:4]) + (1 if q == 4 else 0)}-{q * 3 + 1 if q < 4 else 1:02d}-01"
    print(f"season={season} range=[{air_from}, {air_to})", flush=True)

    DATA.mkdir(parents=True, exist_ok=True)
    HISTORY.mkdir(parents=True, exist_ok=True)
    COVERS.mkdir(parents=True, exist_ok=True)

    bili = BiliClient(CONFIG["bili"]["request_gap"])
    bgm = BgmClient(CONFIG["bgm"]["request_gap"])

    all_videos = []
    ups_meta = []
    for up in CONFIG["ups"]:
        if not up.get("enabled", True):
            continue
        print(f"Fetching UP {up['mid']} {up['name']} ...", flush=True)
        videos, total = fetch_up_videos(bili, up["mid"], args.refresh)
        print(f"  got {len(videos)} / {total} videos", flush=True)
        ups_meta.append({"mid": str(up["mid"]), "name": up["name"], "total": total, "fetched": len(videos)})
        all_videos.extend(videos)

    # 与上次成功抓取的视频增量合并（按 bvid），避免风控导致榜单退化
    video_map = {v["bvid"]: v for v in (load(DATA / "videos.json", []) or [])}
    for v in all_videos:
        video_map[v["bvid"]] = v
    all_videos = sorted(video_map.values(), key=lambda x: x["published"] or 0, reverse=True)
    save(DATA / "videos.json", all_videos)
    print(f"  merged video pool: {len(all_videos)}", flush=True)

    # bangumi-data：当季全量番剧目录（含 bgm id），只拉当季月份文件，不做 53MB submodule
    catalog = fetch_bangumi_catalog(season, args.refresh)
    save(DATA / "bangumi-catalog.json", {
        "generated_at": now_iso(), "season": season, "count": len(catalog),
        "source": "https://github.com/bangumi-data/bangumi-data", "items": catalog,
    })
    print(f"  bangumi-data catalog: {len(catalog)} works for {season}", flush=True)

    # 最近 N 条做 bgm 匹配，避免过多请求
    recent = sorted(all_videos, key=lambda x: x["published"] or 0, reverse=True)[:CONFIG["bili"]["match_recent"]]
    match_cache = load(DATA / "bgm-match-cache.json", {}) or {}
    matches = {}
    print(f"Matching bgm id for {len(recent)} recent videos ...", flush=True)
    for idx, v in enumerate(recent, 1):
        hit = match_bgm(v["title"], bgm, match_cache, catalog)
        if hit:
            matches[v["title"]] = hit
        if idx % 20 == 0:
            print(f"  matched {idx}/{len(recent)}", flush=True)
    save(DATA / "bgm-match-cache.json", match_cache)

    print(f"Fetching bgm season {season} ...", flush=True)
    season_items = bgm.season_subjects(air_from, air_to)

    up_rank, season_rank = build_rank(all_videos, matches, season_items, season)
    for item in season_rank:
        item["season"] = season

    if CONFIG.get("localize_covers") and not args.no_localize:
        print("Localizing covers (top 80) ...", flush=True)
        for item in up_rank[:80]:
            local = localize_cover(item["bvid"], item["cover"])
            if local:
                item["local_cover"] = local

    # 稀饭动漫 Next 榜单（弹幕榜 / 周热榜），数据内联在页面 RSC，纯 GET
    xifan = {}
    if not getattr(args, "no_xifan", False):
        print("Fetching xifan rankings (danmaku_heat / trending_week) ...", flush=True)
        for kind, key, section in [
            ("danmaku_heat", "xifan_danmaku", "all"),
            ("trending_week", "xifan_weekly", "all"),
            ("trending_week", "xifan_weekly_ongoing", "ongoing"),
        ]:
            try:
                payload_x = fetch_xifan_ranking(kind, args.refresh)
                rows = build_xifan_rank(payload_x, section, bgm, match_cache, catalog, match_bgm)
                xifan[key] = rows
                print(f"  {key}: {len(rows)} works", flush=True)
            except Exception as exc:  # noqa: BLE001 - 单个榜单失败不影响其余
                print(f"  [warn] xifan {kind}/{section}: {type(exc).__name__}: {exc}", flush=True)
                xifan[key] = []
        save(DATA / "bgm-match-cache.json", match_cache)

    payload = {
        "meta": {
            "generated_at": now_iso(),
            "current_season": season,
            "season_start": air_from,
            "seasons": sorted({s for s in [season] + [i.get("season") for i in up_rank] if s}, reverse=True),
            "ups": ups_meta,
            "total_videos": len(all_videos),
            "matched_videos": len(matches),
            "catalog_count": len(catalog),
            "sources": {
                "bilibili": "https://space.bilibili.com/690151424",
                "bgm_api": CONFIG["bgm"]["api"],
                "bgm_image": "https://" + CONFIG["bgm"]["image_host"],
                "xifan": "https://next.xifanacg.com/rankings",
            },
        },
        "rankings": {
            "up": up_rank,
            "bgm_season": season_rank,
            **xifan,
        },
    }
    save(DATA / "data.json", payload)
    save(HISTORY / f"{season}.json", payload)
    print(f"Done. {len(up_rank)} works, {len(season_rank)} season subjects -> data/data.json", flush=True)


if __name__ == "__main__":
    main()
