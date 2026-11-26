"""图片相关操作的统一模块：候选提取、过滤校验、下载落盘。

包含：
    1. 落盘配置     图片根目录、热点文件夹映射（topics.json）、大小/尺寸阈值
    2. 候选提取     正文 img / 懒加载 data-src / og:image / JSON-LD 结构化封面
    3. 过滤校验     URL/上下文关键词黑名单 + Pillow 视觉特征（logo/横幅条识别）
    4. 下载保存     按热点分目录、UUIDv7 命名、多 UA/Referer 回退
    5. 封面缩略图   SearXNG 返回的 thumbnail 字段下载（作为文章封面候选）

main.py 等调用方只 import 本模块，不直接触碰下载/过滤细节。
"""

import json
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urljoin
from uuid import UUID

import requests

try:
    # 用于识别站点 logo / 横幅条；未安装时只做基于 URL/上下文的过滤
    from PIL import Image as PILImage
except ImportError:
    PILImage = None

try:
    # Python 3.14+ 内置 UUIDv7
    from uuid import uuid7
except ImportError:
    # 兼容 Python 3.9~3.13：按 RFC 9562 生成 UUIDv7
    def uuid7() -> UUID:
        ms = int(time.time() * 1000) & ((1 << 48) - 1)
        value = (
            (ms << 80)
            | (0x7 << 76)
            | (secrets.randbits(12) << 64)
            | (0b10 << 62)
            | secrets.randbits(62)
        )
        return UUID(int=value)


# ========== 1. 请求头 ==========
COMMON_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
# 部分图床（如 itc.cn）按 UA 黑名单拦截旧版 Chrome，失败时依次回退这些 UA
IMAGE_FALLBACK_UAS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0",
    "curl/8.22.0",
)

ARTICLE_HEADERS = {
    "User-Agent": COMMON_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


# ========== 2. 落盘配置 ==========
# 图片落地：保存到项目根的 images/ 目录，对外只暴露相对路径
IMAGE_DIR_NAME = "images"
IMAGE_DIR = Path(__file__).resolve().parent / IMAGE_DIR_NAME
IMAGE_DOWNLOAD_TIMEOUT = 15
MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 单张上限 20MB，避免异常响应撑爆磁盘
TOPIC_INDEX_FILE = IMAGE_DIR / "topics.json"  # 热点标题 <-> uuid7 文件夹映射，便于排查
TOPIC_INDEX_LOCK = threading.Lock()
_TOPIC_DIRS = {}                     # 标题 -> uuid7 文件夹（内存侧记录）

# 同一热点下同一 URL 复用已保存文件；不同热点各存一份，便于排查
_IMAGE_CACHE = {}                    # (topic, source_url) -> 本地相对路径
_IMAGE_CACHE_LOCK = threading.Lock()


def load_topic_index() -> dict:
    """读取热点标题与文件夹的映射；文件损坏时返回空表重新建立。"""
    try:
        with open(TOPIC_INDEX_FILE, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_topic_index(index: dict):
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = TOPIC_INDEX_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(index, fp, ensure_ascii=False, indent=2)
    tmp.replace(TOPIC_INDEX_FILE)


def get_topic_dir(topic: str) -> tuple[Path, str]:
    """每个热点标题一个 uuid7 文件夹；同名热点复用，映射写入 topics.json。"""
    with TOPIC_INDEX_LOCK:
        index = load_topic_index()
        record = index.get(topic)
        folder = record.get("folder", "") if isinstance(record, dict) else ""
        if not folder or not (IMAGE_DIR / folder).is_dir():
            folder = str(uuid7())
            (IMAGE_DIR / folder).mkdir(parents=True, exist_ok=True)
        now = datetime.now().isoformat(timespec="seconds")
        index[topic] = {
            "folder": folder,
            "created_at": record.get("created_at", now) if isinstance(record, dict) else now,
            "last_seen": now,
        }
        save_topic_index(index)
        _TOPIC_DIRS[topic] = folder
    return IMAGE_DIR / folder, folder


# ========== 3. 过滤配置 ==========
# 图片过滤：用完整词，避免 "ad" / "qr" / "wx" 这类短子串误杀正文图
BAD_IMG_PATTERNS = (
    "logo", "qrcode", "qr_code", "erweima", "ercode", "二维码", "扫码",
    "icon", "favicon", "share", "wechat", "weixin", "公众号",
    "pengyouquan", "moments", "layershare",
    "banner", "advert", "ads/", "/ad_", "loading", "placeholder",
    "code.png", "code.jpg", "code_wx", "code_app",
)
MIN_IMG_SIZE = 10 * 1024  # 10KB，更小的多半是装饰图
MAX_IMAGES_PER_ARTICLE = 10

# 上下文品牌词：只检查 alt/class/id/父元素文本，不检查 URL，避免误杀标题含这些词的文章
BRAND_CONTEXT_PATTERNS = (
    "视界", "水印", "watermark", "brand", "site-logo", "自媒体",
    "版权所有", "转载请", "官方微信", "头条号", "百家号",
)
# 视觉特征：logo / 横幅条通常是小图、宽高比悬殊、大面积白底且四角同色
MIN_IMG_WIDTH = 320
MIN_IMG_HEIGHT = 200
MAX_IMG_RATIO = 3.2
WHITE_BG_RATIO = 0.72
CORNER_SPREAD_MAX = 24
# 正文图优先；只有正文拿不到图时才用 meta / JSON-LD 封面兜底
ORIGIN_PRIORITY = {"page": 0, "body": 0, "jsonld": 1, "meta": 2}


def normalize_img_url(page_url: str, src: str) -> str:
    """把 src / srcset / meta 里的图片地址规范化成绝对 http(s) URL。"""
    if not src:
        return ""
    src = src.strip().replace("\\/", "/")
    if not src or src.lower().startswith(("data:", "javascript:", "about:")):
        return ""
    abs_url = urljoin(page_url, src)
    if not abs_url.lower().startswith(("http://", "https://")):
        return ""
    return abs_url.split("#", 1)[0]


def is_bad_image(candidate: dict) -> bool:
    # 只检查 URL、alt 和 img 自身属性；父节点正文段落不参与，避免误杀正常配图
    text = " ".join((
        candidate.get("img_url", ""),
        candidate.get("alt", ""),
        candidate.get("attr_hint", ""),
    )).lower()
    if any(word in text for word in BAD_IMG_PATTERNS):
        return True
    return any(word in text for word in BRAND_CONTEXT_PATTERNS)


def collect_image_candidates(html: str, body_html: str, page_url: str):
    """正文 img + 原始页面 og:image / JSON-LD，解决 trafilatura 丢图的问题。"""
    candidates = []
    seen = set()

    def img_context(img) -> tuple[str, str]:
        """返回 (短属性提示, 父节点文本)；品牌词只匹配前者，避免正文误杀。"""
        attrs = []
        for attr in ("class", "id", "title"):
            value = img.get(attr)
            if isinstance(value, str):
                attrs.append(value)
            elif isinstance(value, list):
                attrs.extend(value)
        attr_hint = " ".join(attrs).strip()
        parent = img.getparent()
        parent_text = ""
        if parent is not None:
            try:
                parent_text = (parent.text or "")[:100].strip()
            except Exception:
                pass
        return attr_hint, parent_text

    def add(src, alt="", origin="body", context="", attr_hint=""):
        abs_url = normalize_img_url(page_url, src)
        if not abs_url or abs_url in seen:
            return
        seen.add(abs_url)
        candidates.append({
            "img_url": abs_url,
            "alt": (alt or "").strip(),
            "origin": origin,
            "context": (context or "").strip()[:200],
            "attr_hint": (attr_hint or "").strip()[:120],
        })

    # 1) trafilatura 提取出的正文图片（已经排除了侧边栏大部分装饰）
    if body_html:
        try:
            from lxml import etree
            tree = etree.fromstring(body_html, etree.HTMLParser())
            for img in tree.xpath(".//img"):
                src = (
                    img.get("src")
                    or img.get("data-src")
                    or img.get("data-original")
                    or ""
                )
                attr_hint, parent_text = img_context(img)
                ctx = f"{attr_hint} {parent_text}".strip()
                add(src, img.get("alt", ""), "body", ctx, attr_hint)
                srcset = img.get("srcset") or ""
                if srcset:
                    add(srcset.split(",")[0].strip().split(" ")[0], img.get("alt", ""), "body", ctx, attr_hint)
        except Exception as e:
            print(f"⚠️ 正文图片解析失败 {page_url} | {e}")

    # 2) 原始 HTML 正文区域：搜狐等站点用懒加载，src 为空、真实地址在 data-src
    from lxml import etree
    doc = etree.HTML(html)
    if doc is not None:
        body_scope = None
        for xpath in (
            "//*[@id='mp-editor']", "//article", "//*[@id='articleContent']",
            "//*[@id='contentText']", "//*[@class='article-content']",
        ):
            for node in doc.xpath(xpath):
                if node.xpath(".//img"):
                    body_scope = node
                    break
            if body_scope is not None:
                break
        if body_scope is not None:
            for img in body_scope.xpath(".//img"):
                for attr in ("data-src", "data-original", "src"):
                    src = img.get(attr) or ""
                    # 排除以加密串形式存放的 data-src（不是 http(s) 或路径形式）
                    if src.startswith(("http://", "https://", "//", "/")):
                        attr_hint, parent_text = img_context(img)
                        add(src, img.get("alt", ""), "page",
                            f"{attr_hint} {parent_text}".strip(), attr_hint)
                        break

        # 3) 原页面的封面图 / 结构化数据，作为正文无图时的兜底
        for meta in doc.xpath("//meta"):
            key = (meta.get("property") or meta.get("name") or "").lower()
            if key in {"og:image", "og:image:url", "twitter:image", "twitter:image:src"}:
                add(meta.get("content", ""), "封面图", "meta", f"meta {key}", key)
        for script in doc.xpath('//script[@type="application/ld+json"]'):
            try:
                payload = json.loads(script.text or "")
            except (TypeError, ValueError):
                continue
            stack = [payload]
            while stack:
                node = stack.pop()
                if isinstance(node, dict):
                    image = node.get("image")
                    title_hint = node.get("headline") or node.get("name") or ""
                    if isinstance(image, str):
                        add(image, title_hint, "jsonld", "jsonld image", "jsonld")
                    elif isinstance(image, list):
                        for value in image:
                            if isinstance(value, str):
                                add(value, title_hint, "jsonld", "jsonld image", "jsonld")
                            elif isinstance(value, dict):
                                add(value.get("url", ""), title_hint, "jsonld", "jsonld image", "jsonld")
                    stack.extend(node.values())
                elif isinstance(node, list):
                    stack.extend(node)
    return candidates


def infer_image_ext(img_url: str, content_type: str) -> str:
    """优先按 Content-Type 定扩展名，兜底看 URL 路径；空串表示不是图片。"""
    ctype = (content_type or "").split(";", 1)[0].strip().lower()
    ext_map = {
        "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
        "image/gif": ".gif", "image/webp": ".webp", "image/bmp": ".bmp",
        "image/avif": ".avif", "image/svg+xml": ".svg",
    }
    if ctype in ext_map:
        return ext_map[ctype]
    path = urlparse(img_url).path.lower()
    for candidate in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif", ".svg"):
        if path.endswith(candidate):
            return ".jpg" if candidate == ".jpeg" else candidate
    return ""


def is_brand_banner_image(path: Path) -> tuple[bool, str]:
    """识别站点 logo / 横幅条：小图、宽高比悬殊、大面积白底且四角同色。"""
    if PILImage is None:
        return False, ""
    try:
        with PILImage.open(path) as im:
            w, h = im.size
            if w <= 0 or h <= 0:
                return True, "图片尺寸无效"
            ratio = w / h
            if w < MIN_IMG_WIDTH or h < MIN_IMG_HEIGHT:
                return True, f"图片过小 {w}x{h}，疑似图标"
            if ratio > MAX_IMG_RATIO or ratio < 1.0 / MAX_IMG_RATIO:
                return True, f"宽高比 {ratio:.2f} 悬殊，疑似横幅/logo"
            thumb = im.convert("RGB").resize((64, 64))
            pixels = list(thumb.getdata())
            white = sum(
                1 for r, g, b in pixels if r > 240 and g > 240 and b > 240
            ) / len(pixels)
            corners = [
                thumb.getpixel((x, y)) for x, y in ((0, 0), (63, 0), (0, 63), (63, 63))
            ]
            spread = max(max(c) for c in corners) - min(min(c) for c in corners)
            if white >= WHITE_BG_RATIO and spread <= CORNER_SPREAD_MAX:
                return True, f"白底占比 {white:.0%} 且四角同色，疑似站点标识"
    except Exception:
        # 读图失败不阻断保存； Pillow 不支持的格式交由下游判断
        return False, ""
    return False, ""


def _build_header_variants(page_url: str):
    """按 UA x Referer 组合生成下载请求头，命中防盗链时逐个回退。"""
    parsed = urlparse(page_url)
    site_root = f"{parsed.scheme}://{parsed.netloc}/"
    image_accept = "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"
    variants = []
    for ua in (COMMON_UA, *IMAGE_FALLBACK_UAS):
        for referer in (page_url, site_root, ""):
            headers = {
                **ARTICLE_HEADERS,
                "User-Agent": ua,
                "Accept": image_accept if ua == COMMON_UA else "*/*",
            }
            if referer:
                headers["Referer"] = referer
            variants.append(headers)
    return variants


def save_image(candidate: dict, page_url: str, topic: str = "") -> dict:
    """下载候选图片，按热点分目录、UUIDv7 命名保存，对外只给本地相对路径。

    成功: {"saved": True, "img_url": "images/<topic_uuid7>/<img_uuid7>.jpg", ...}
    失败: {"saved": False, "source_url": ..., "error": ...}
    """
    img_url = candidate["img_url"]
    if topic:
        topic_dir, folder = get_topic_dir(topic)
        rel_prefix = f"{IMAGE_DIR_NAME}/{folder}"
    else:
        topic_dir, folder = IMAGE_DIR, ""
        rel_prefix = IMAGE_DIR_NAME

    # 同一热点下同一 URL 复用已保存文件；不同热点各存一份，便于排查
    cache_key = (topic, img_url)
    with _IMAGE_CACHE_LOCK:
        cached = _IMAGE_CACHE.get(cache_key)
    if cached:
        try:
            size = (IMAGE_DIR.parent / cached).stat().st_size
        except OSError:
            size = 0
        return {
            "saved": True, "from_cache": True,
            "img_url": cached, "local_path": cached,
            "source_url": img_url,
            "alt": candidate.get("alt", ""),
            "origin": candidate.get("origin", ""),
            "file_size": size,
        }

    header_variants = _build_header_variants(page_url)

    last_error = "未知错误"
    tmp_path = None
    for headers in header_variants:
        resp = None
        try:
            resp = requests.get(
                img_url, headers=headers, timeout=IMAGE_DOWNLOAD_TIMEOUT,
                stream=True, allow_redirects=True,
            )
            if resp.status_code >= 400:
                last_error = f"HTTP {resp.status_code}"
                continue
            ext = infer_image_ext(img_url, resp.headers.get("Content-Type", ""))
            if not ext:
                last_error = f"非图片响应: {resp.headers.get('Content-Type', '')[:60]}"
                continue

            topic_dir.mkdir(parents=True, exist_ok=True)
            name = f"{uuid7()}{ext}"
            tmp_path = topic_dir / f".{name}.part"
            size = 0
            with open(tmp_path, "wb") as fp:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    fp.write(chunk)
                    size += len(chunk)
                    if size > MAX_IMAGE_BYTES:
                        raise ValueError(f"图片超过 {MAX_IMAGE_BYTES} 字节上限")
            if size < MIN_IMG_SIZE:
                last_error = f"图片过小: {size} 字节"
                tmp_path.unlink(missing_ok=True)
                tmp_path = None
                continue

            # 内容本身像 logo / 横幅条时换 Referer、UA 也没用，直接丢弃
            brand, brand_reason = is_brand_banner_image(tmp_path)
            if brand:
                last_error = brand_reason
                tmp_path.unlink(missing_ok=True)
                tmp_path = None
                break

            local_path = f"{rel_prefix}/{name}"
            tmp_path.replace(topic_dir / name)
            tmp_path = None
            with _IMAGE_CACHE_LOCK:
                _IMAGE_CACHE[cache_key] = local_path
            return {
                "saved": True, "from_cache": False,
                "img_url": local_path, "local_path": local_path,
                "source_url": img_url,
                "alt": candidate.get("alt", ""),
                "origin": candidate.get("origin", ""),
                "file_size": size,
            }
        except (requests.RequestException, OSError, ValueError) as exc:
            last_error = str(exc)
        finally:
            if resp is not None:
                resp.close()
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass
                tmp_path = None

    return {
        "saved": False, "source_url": img_url,
        "alt": candidate.get("alt", ""),
        "origin": candidate.get("origin", ""),
        "error": last_error,
    }


# ========== 4. SearXNG 封面缩略图 ==========
MIN_THUMB_SIZE = 3 * 1024  # 缩略图本来就小，阈值放宽到 3KB
_THUMB_CACHE = {}          # (topic, thumb_url) -> 本地相对路径
_THUMB_CACHE_LOCK = threading.Lock()


def extract_thumbnail_url(value) -> str:
    """从 SearXNG 结果的 thumbnail 字段提取图片 URL。

    各引擎返回格式不一：多数是字符串，部分引擎（如 bing images 系列）
    返回 {"src": ..., "url": ...} 之类的字典，这里统一兼容。
    """
    if isinstance(value, dict):
        value = value.get("src") or value.get("url") or value.get("srcset") or ""
    if not isinstance(value, str):
        return ""
    return value.strip()


def save_thumbnail(thumb_url: str, page_url: str, topic: str = "") -> str:
    """下载 SearXNG 封面缩略图，保存为文章封面候选，返回本地相对路径。

    与正文配图不同：thumbnail 由搜索引擎给出，天然对应文章封面，
    所以不做 logo/横幅视觉过滤，尺寸阈值也放宽；失败返回空串不阻断主流程。
    """
    url = extract_thumbnail_url(thumb_url)
    if not url.startswith(("http://", "https://")):
        return ""

    if topic:
        topic_dir, folder = get_topic_dir(topic)
        rel_prefix = f"{IMAGE_DIR_NAME}/{folder}"
    else:
        topic_dir, folder = IMAGE_DIR, ""
        rel_prefix = IMAGE_DIR_NAME

    cache_key = (topic, url)
    with _THUMB_CACHE_LOCK:
        cached = _THUMB_CACHE.get(cache_key)
    if cached:
        return cached

    last_error = "未知错误"
    tmp_path = None
    resp = None
    try:
        resp = requests.get(
            url,
            headers={**ARTICLE_HEADERS, "Referer": page_url},
            timeout=IMAGE_DOWNLOAD_TIMEOUT,
            stream=True, allow_redirects=True,
        )
        if resp.status_code >= 400:
            return ""
        ext = infer_image_ext(url, resp.headers.get("Content-Type", ""))
        if not ext:
            return ""

        topic_dir.mkdir(parents=True, exist_ok=True)
        name = f"{uuid7()}{ext}"
        tmp_path = topic_dir / f".{name}.part"
        size = 0
        with open(tmp_path, "wb") as fp:
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                fp.write(chunk)
                size += len(chunk)
                if size > MAX_IMAGE_BYTES:
                    raise ValueError(f"缩略图超过 {MAX_IMAGE_BYTES} 字节上限")
        if size < MIN_THUMB_SIZE:
            return ""
        local_path = f"{rel_prefix}/{name}"
        tmp_path.replace(topic_dir / name)
        tmp_path = None
        with _THUMB_CACHE_LOCK:
            _THUMB_CACHE[cache_key] = local_path
        return local_path
    except (requests.RequestException, OSError, ValueError) as exc:
        last_error = str(exc)
        print(f"⚠️ 封面缩略图下载失败 {url[:80]} | {last_error}")
        return ""
    finally:
        if resp is not None:
            resp.close()
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
