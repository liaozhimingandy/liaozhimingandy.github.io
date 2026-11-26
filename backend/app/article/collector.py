"""热点新闻采集阶段（原 main.py）。

职责单一：抓微博/百度热搜 -> SearXNG 搜新闻 -> 正文/图片抓取入库。
只做一次采集（run_collect），轮询调度由 scheduler.py 负责。

异步模型：
    run_collect() 是协程，运行在事件循环上；数据读写走 session_scope
    （独立会话 + 结束自动提交）+ TopicDAO/NewsDAO，网络/正文提取等
    阻塞操作包在 asyncio.to_thread 里，不阻塞事件循环。

运行方式（包内相对导入）：
    py -3.13 -m app.article.collector      # 单次采集
    py -3.13 -m app.article.pipeline --stage collect
"""

import asyncio
import json
import re
import threading
import time
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

import requests

from ..core import session_scope
from .dal import NewsDAO, TopicDAO
from .image_store import (
    ARTICLE_HEADERS,
    ORIGIN_PRIORITY,
    MAX_IMAGES_PER_ARTICLE,
    collect_image_candidates,
    get_topic_dir,
    is_bad_image,
    save_image,
    save_thumbnail,
    extract_thumbnail_url,
)

try:
    import jieba  # 分词相关性判断；缺失时退化为字符级重叠
except Exception:  # jieba 缺失不阻塞采集
    jieba = None

try:
    import trafilatura  # 正文提取核心依赖；缺失时采集阶段不可用
except Exception as _trafilatura_exc:
    trafilatura = None
    _TRAFILATURA_ERROR = f"{type(_trafilatura_exc).__name__}: {_trafilatura_exc}"
else:
    _TRAFILATURA_ERROR = ""

try:
    from lxml import etree  # 仅用于 <title> 兜底提取
except Exception:
    etree = None


# 政治、军事类屏蔽词
BLACK_POLI_MIL = {
    "战区", "军演", "导弹", "战机", "军舰", "航母", "国防部",
    "外交", "会晤", "会谈", "领导人", "总理", "总统", "大选",
    "制裁", "冲突", "战争", "战事", "俄乌", "巴以", "边境",
    "国防", "军队", "武警", "兵变", "政变"
}


COMMON_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)

# 按用途分开定义，避免后面的赋值把前面的请求头覆盖掉。
# 微博 /ajax/ 接口会校验 Referer：必须是 weibo.com 的普通页面，
# 不能缺省，也不能是 /ajax/... 路径，否则返回 403 {"error":"Forbidden"}。
WEIBO_HEADERS = {
    "User-Agent": COMMON_UA,
    "Referer": "https://weibo.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
BAIDU_HEADERS = {
    "User-Agent": COMMON_UA,
    "Referer": "https://top.baidu.com/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
SEARCH_HEADERS = {"User-Agent": COMMON_UA}
# 正文抓取用请求头定义在 image_store（图片下载共用同一套 UA 体系）


def filter_hot_topic(title: str) -> bool:
    # 军政黑名单：返回 True 表示保留，False 表示过滤
    if any(b in title for b in BLACK_POLI_MIL):
        return False
    return True


def fetch_weibo_hot():
    url = "https://weibo.com/ajax/side/hotSearch"
    resp = None
    try:
        resp = requests.get(url, headers=WEIBO_HEADERS, timeout=15)
        if resp.status_code == 403:
            print(f"❌ 微博热搜 403，响应体：{resp.text[:200]}")
            return []
        resp.raise_for_status()
        data = resp.json()
        res = []
        payload = data.get("data") or {}
        # 置顶政务话题 + 实时热搜，两种结构都兼容
        entries = list(payload.get("realtime") or [])
        gov = payload.get("hotgov")
        if isinstance(gov, list):
            entries = gov + entries
        elif isinstance(gov, dict):
            entries = [gov] + entries
        for item in entries:
            if not isinstance(item, dict):
                continue
            title = (item.get("note") or item.get("word") or "").strip()
            if not title:
                continue
            try:
                hot_score = int(item.get("num") or item.get("hot_score") or 0)
            except (TypeError, ValueError):
                hot_score = 0
            res.append({
                "title": title,
                "source": "weibo",
                "hot_score": hot_score,
            })
        print(f"✅ 微博热搜拿到 {len(res)} 条")
        return res
    except Exception as e:
        detail = f" | 响应体：{resp.text[:200]}" if resp is not None else ""
        print(f"❌ 微博热搜抓取失败：{e}{detail}")
        return []


def fetch_baidu_hot():
    url = "https://top.baidu.com/board?tab=realtime"
    try:
        resp = requests.get(url, headers=BAIDU_HEADERS, timeout=15)
        resp.raise_for_status()
        # 正则提取注释里的s-data
        match = re.search(r'<!--s-data:(.*?)-->', resp.text, re.S)
        if not match:
            print("❌ 百度热搜：没有找到s-data")
            return []
        raw_json = match.group(1)
        data = json.loads(raw_json)
        res = []
        # 遍历cards
        for card in data["data"]["cards"]:
            for item in card["content"]:
                title = item.get("word", "")
                hot_score = item.get("hotScore", 0)
                if title:
                    res.append({
                        "title": title,
                        "source": "baidu",
                        "hot_score": int(hot_score)
                    })
        print(f"✅ 百度热搜拿到 {len(res)} 条")
        return res
    except Exception as e:
        print(f"❌ 百度热搜抓取失败：{e}")
        return []


# searxng地址
SEARXNG_URL = "http://127.0.0.1:8080/search"
MAX_NEWS_PER_TOPIC = 4  # 每个热点最多拿几条新闻链接
MAX_TOPICS = 10         # 一次采集最多处理几个热点
TOPIC_INTERVAL = 3.0    # 热点之间的间隔，降低百度风控触发概率
MAX_SEARCH_RETRIES = 3  # 失败后重试 3 次，即最多请求 4 次
SEARCH_RETRY_BASE_DELAY = 1.5  # 指数退避基数：1.5s / 3s / 6s
SEARCH_TIMEOUT = 60

# 域名黑名单：不要豆瓣、知乎这类UGC
BLACK_DOMAINS = {
    "douban.com", "zhihu.com", "xiaohongshu.com", "bilibili.com",
    "tieba.baidu.com", "baike.baidu.com", "maoyan.com", "mtime.com"
}

def get_domain(url: str):
    """提取域名，去掉www."""
    try:
        dom = urlparse(url).netloc.lower()
        return dom.replace("www.", "")
    except Exception:
        return ""

def is_black_url(url):
    dom = get_domain(url)
    return any(bad in dom for bad in BLACK_DOMAINS)

def title_relevant(topic, title, threshold=0.20):
    """分词简单判断标题相关性，太低就丢弃；jieba 缺失时退化到字符二元组。"""
    if jieba is not None:
        words_topic = set(jieba.lcut(topic))
        words_title = set(jieba.lcut(title))
    else:
        words_topic = {topic[i:i + 2] for i in range(max(len(topic) - 1, 0))} or {topic}
        words_title = {title[i:i + 2] for i in range(max(len(title) - 1, 0))} or {title}
    if not words_topic:
        return True
    inter = words_topic & words_title
    return len(inter) / len(words_topic) >= threshold


# 本次运行已尝试采集的新闻链接（规范化 key），跨热点复用，避免同一篇文章反复抓
_COLLECTED_URL_KEYS = set()
_COLLECTED_URL_LOCK = threading.Lock()


async def claim_news_url(url: str, topic: str = "",
                         news_dao: NewsDAO | None = None) -> bool:
    """返回 True 表示允许采集；本次运行或数据库里已有该链接则跳过。"""
    from .utils import normalize_news_url

    key = normalize_news_url(url)
    if not key:
        print(f"  ⏭️ 链接无法规范化，跳过：{url[:80]} <- {topic}")
        return False
    with _COLLECTED_URL_LOCK:
        if key in _COLLECTED_URL_KEYS:
            print(f"  ⏭️ 跳过重复链接（本次运行）：{url[:80]} <- {topic}")
            return False
        # 先占位，避免同一链接被后续热点再次抓；采集失败也不重复尝试
        _COLLECTED_URL_KEYS.add(key)
    if news_dao is not None and await news_dao.is_collected(url):
        print(f"  ⏭️ 跳过已入库链接：{url[:80]} <- {topic}")
        return False
    return True


def fetch_news_urls_by_topic(topic: str):
    """根据热点标题调用 SearXNG；网络错误 / HTTP 错误 / 空结果都重试。

    同步阻塞函数：由 run_collect 放进 asyncio.to_thread 执行。
    """
    from .utils import normalize_news_url

    params = {
        "q": topic,
        "categories": "news",
        "format": "json",
        "lang": "zh",
        "time_range": "day"
    }
    last_error = ""
    for attempt in range(MAX_SEARCH_RETRIES + 1):
        try:
            resp = requests.get(
                SEARXNG_URL, params=params, headers=SEARCH_HEADERS,
                timeout=SEARCH_TIMEOUT,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if not results:
                # bing news 偶尔返回空 body，SearXNG 表现为 200 + 空 results
                raise ValueError("SearXNG 返回空结果（引擎空响应或验证码）")
            out_urls = []
            seen_in_response = set()
            dup_skipped = 0
            for item in results:
                url = item.get("url")
                res_title = item.get("title", "")
                if not url:
                    continue
                # 域名黑名单过滤
                if is_black_url(url):
                    continue
                # 同一批结果里可能返回同一篇文章的多个镜像/分享链接，先在同一话题内去重
                key = normalize_news_url(url)
                if not key:
                    continue
                if key in seen_in_response:
                    dup_skipped += 1
                    continue
                seen_in_response.add(key)
                out_urls.append({
                    "topic": topic,
                    "news_title": res_title,
                    "url": url,
                    # SearXNG 的封面缩略图（字符串 URL 或 {src:...} 字典，统一提取）
                    "thumbnail": extract_thumbnail_url(item.get("thumbnail")),
                })
            print(
                f"【{topic}】searxng返回{len(results)}条，"
                f"同话题重复跳过{dup_skipped}条，过滤后保留{len(out_urls)}条"
            )
            return out_urls[:MAX_NEWS_PER_TOPIC]
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < MAX_SEARCH_RETRIES:
                delay = SEARCH_RETRY_BASE_DELAY * (2 ** attempt)
                print(
                    f"【{topic}】搜索失败（{last_error}），{delay:.1f}s 后重试 "
                    f"{attempt + 1}/{MAX_SEARCH_RETRIES}"
                )
                time.sleep(delay)
    print(f"【{topic}】搜索失败，已重试 {MAX_SEARCH_RETRIES} 次：{last_error}")
    return []


def extract_article(url: str, topic: str = ""):
    """正文/图片抓取与提取（同步阻塞，由 to_thread 调用）。"""
    if trafilatura is None:
        print(f"❌ trafilatura 未安装，无法提取正文（pip install trafilatura）：{url}")
        return None
    try:
        resp = requests.get(url, headers=ARTICLE_HEADERS, timeout=15)
        # chardet 不再作为硬依赖：requests 自带 charset_normalizer 探测编码
        encoding = resp.apparent_encoding or resp.encoding or "utf-8"
        html = resp.content.decode(encoding, errors="replace")

        body_html = trafilatura.extract(html, output_format="html", include_images=True) or ""
        meta_raw = trafilatura.extract(
            html, output_format="json", include_links=False, include_images=False
        )
        meta = {}
        if meta_raw:
            try:
                meta = json.loads(meta_raw)
            except (TypeError, ValueError):
                meta = {}

        candidates = collect_image_candidates(html, body_html, url)
        good_candidates = [item for item in candidates if not is_bad_image(item)]

        final_imgs = []
        failed_imgs = []
        # 正文图优先；拿到图就不再用 meta / JSON-LD 兜底，避免混入站点标识图
        levels = sorted({ORIGIN_PRIORITY.get(item["origin"], 3) for item in good_candidates})
        for level in levels:
            batch = [
                item for item in good_candidates
                if ORIGIN_PRIORITY.get(item["origin"], 3) == level
            ][:MAX_IMAGES_PER_ARTICLE * 3]
            if not batch:
                continue
            # 并发下载直接落盘并校验，省掉额外的 HEAD/Range 探测请求
            with ThreadPoolExecutor(max_workers=8) as pool:
                saved = list(pool.map(lambda item: save_image(item, url, topic), batch))
            final_imgs.extend(item for item in saved if item.get("saved"))
            failed_imgs.extend(item for item in saved if not item.get("saved"))
            if final_imgs:
                break
        final_imgs = final_imgs[:MAX_IMAGES_PER_ARTICLE]

        text = meta.get("text") or trafilatura.extract(html, output_format="txt") or ""
        title = meta.get("title") or ""
        if not title and etree is not None:
            doc = etree.HTML(html)
            if doc is not None and doc.xpath("//title/text()"):
                title = doc.xpath("//title/text()")[0].strip()

        article = {
            "url": url,
            "topic": topic,
            "title": title,
            "author": meta.get("author", ""),
            "date": meta.get("date", ""),
            "text": text,
            "language": meta.get("language", ""),
            "images": final_imgs,          # img_url 为 images/<uuid7>.ext 本地相对路径
            "failed_images": failed_imgs,  # 下载失败的候选，便于排查防盗链
        }
        if len(text) < 250:
            print(f"⚠️ 正文过短，丢弃：{url}")
            return None
        return article
    except Exception as e:
        print(f"❌ 采集异常 {url} | {e}")
        return None


async def run_collect() -> dict:
    """采集阶段：抓热点 -> 搜新闻 -> 正文/图片入库。返回本次统计。

    数据写入走独立会话（session_scope）：热点入库与每条新闻入库后
    立即 commit，采集进行到一半崩溃不至于整轮白跑。
    """
    if trafilatura is None:
        print(f"❌ 采集阶段依赖缺失（trafilatura：{_TRAFILATURA_ERROR}），本次跳过")
        return {"topics": 0, "articles": 0, "skipped": 0, "error": "deps_missing"}

    stats = {"topics": 0, "articles": 0, "skipped": 0}

    async with session_scope() as session:
        topic_dao = TopicDAO(session)
        news_dao = NewsDAO(session)

        wb = await asyncio.to_thread(fetch_weibo_hot)
        bd = await asyncio.to_thread(fetch_baidu_hot)
        all_hot = wb + bd
        valid_hot = [h for h in all_hot if filter_hot_topic(h["title"])]
        inserted = await topic_dao.save_topics(valid_hot)
        await session.commit()
        print(f"[collector] 热点入库：提交 {len(valid_hot)} 条，新增 {inserted} 条")
        stats["topics"] = len(valid_hot)

        # 按热度从高到低排序
        valid_hot.sort(key=lambda x: x["hot_score"], reverse=True)

        if not valid_hot:
            print("没有可用热点，退出")
            return stats

        for idx, hot in enumerate(valid_hot[:MAX_TOPICS]):
            if idx:
                await asyncio.sleep(TOPIC_INTERVAL)
            print(f"\n===== 热点：{hot['title']} ({hot['source']}, {hot['hot_score']}) =====")
            topic_dir, folder = get_topic_dir(hot['title'])
            print(f"📁 图片目录：images/{folder}/（标题映射记录于 images/topics.json）")
            data = await asyncio.to_thread(fetch_news_urls_by_topic, hot['title'])
            for item in data:
                # 跨热点、跨运行拦截重复链接；命中就不发正文请求，更不重复下载图片
                if not await claim_news_url(item['url'], hot['title'], news_dao):
                    stats["skipped"] += 1
                    continue
                article = await asyncio.to_thread(extract_article, item['url'],
                                                  topic=hot['title'])
                # SearXNG 封面缩略图：与正文配图独立采集，作为文章封面候选
                thumbnail = ""
                if item.get("thumbnail"):
                    thumbnail = await asyncio.to_thread(
                        save_thumbnail, item["thumbnail"], item["url"], hot["title"])
                if article:
                    print(f"标题：{article['title']} | 文章链接：{article['url']} | 正文 {len(article['text'])} 字 | 图片 {len(article['images'])} 张")
                    if thumbnail:
                        print(f"  🎯 封面缩略图：{thumbnail}  <-  {item['thumbnail']}")
                    for img in article['images']:
                        print(f"  🖼️ {img['img_url']}  <-  {img['source_url']}")
                    art = {
                        "url": article["url"],
                        "title": article.get("title", ""),
                        "author": article.get("author", ""),
                        "date": article.get("date", ""),
                        "text": article.get("text", ""),
                        "images": [
                            {"img_url": img["img_url"], "alt": img.get("alt", "")}
                            for img in article["images"]
                        ],
                        "thumbnail": thumbnail,
                        "hot_topic": hot["title"],
                        "hot_source": hot["source"],
                        "hot_score": hot["hot_score"],
                    }
                    if await news_dao.insert_news(art):
                        await session.commit()
                        stats["articles"] += 1
                elif thumbnail:
                    # 正文抓取失败但缩略图拿到了：不建 news 记录（缺正文），只提示留痕
                    print(f"  ⚠️ 正文抓取失败，封面缩略图暂存未入库：{thumbnail}")

    return stats


# 兼容旧调用名：collector.main() 仍然可用
main = run_collect

if __name__ == "__main__":
    asyncio.run(run_collect())
