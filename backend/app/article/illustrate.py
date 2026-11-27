"""文章配图后处理：封面选择 + 正文插图（素材有图才配图）。

采集阶段（collector / image_store）已经把正文图片下载到本地
（images/<热点文件夹>/<uuid7>.jpg），SearXNG 封面缩略图也存在 news.thumbnail。
生成工作流（llm.py）产出的是纯文字 Markdown；落库前由本模块做一次
「配图后处理」：

    1. 选封面     优先正文图（过了 logo/横幅过滤、分辨率达标），
                  没有正文图时兜底封面缩略图；
    2. 正文插图   剩余图片作为独立段落按正文段落均匀分布插入，
                  幂等（图片已在正文则跳过），代码块/表格段落不插；
    3. 平台版本   multi_platform 的文章类字段（公众号/百家/头条/小红书）
                  同样插图；口播稿（script）/标题组/封面提示词不插。

图片 URL 统一写成站点根绝对路径 /images/...（后端 main.py 挂载静态目录），
前端跨源部署时按 API 根重写前缀即可直接展示。
"""

from ..core.logger import logger

import re

# 本地已落盘图片的前缀（image_store.save_image / save_thumbnail 的产物）
IMAGE_LOCAL_PREFIX = "images/"
# 服务端静态目录挂载点（main.py 与这里保持一致）
IMAGE_URL_PREFIX = "/images/"

# multi_platform 里需要插图的文章类字段；script 是口播稿、title_list 是标题组、
# cover_prompt 是封面提示词，都不适合插图
ARTICLE_PLATFORM_KEYS = ("official", "baijia", "toutiao", "xiaohongshu")

# 正文最多插几张：素材图往往十来张，全部塞进正文会喧宾夺主
MAX_INLINE_IMAGES = 6

# 图注（alt）长度上限
_MAX_ALT_LEN = 60


def _sanitize_alt(alt: str) -> str:
    """清洗图注：去掉会破坏 Markdown 图片语法的字符，截断到安全长度。"""
    text = re.sub(r"[\[\]()\n\r\t]+", " ", str(alt or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:_MAX_ALT_LEN]


def normalize_candidates(images: list, thumbnails: list[str] | None = None) -> list[dict]:
    """素材图片 -> 去重后的候选列表 [{img_url, alt}]，只保留本地已落盘的图。

    images 来自 event.images（cluster 聚合产物），img_url 是本地相对路径；
    thumbnails 来自 news.thumbnail（SearXNG 封面缩略图，同为本地路径），
    排在正文图之后作为兜底候选。远程 URL（未下载成功的）不用于配图。
    """
    candidates: list[dict] = []
    seen: set[str] = set()

    def _add(url: str, alt: str) -> None:
        url = str(url or "").strip().replace("\\", "/")
        if not url.startswith(IMAGE_LOCAL_PREFIX) or url in seen:
            return
        seen.add(url)
        candidates.append({"img_url": f"{IMAGE_URL_PREFIX}{url[len(IMAGE_LOCAL_PREFIX):]}",
                           "alt": _sanitize_alt(alt)})

    for item in images or []:
        if isinstance(item, dict):
            _add(item.get("img_url"), item.get("alt"))
        elif isinstance(item, str):
            _add(item, "")
    for thumb in thumbnails or []:
        _add(thumb, "封面图")
    return candidates


def pick_cover(candidates: list[dict]) -> tuple[dict | None, list[dict]]:
    """选封面：第一张候选为封面，其余作为正文插图候选。

    返回 (封面, 插图候选)；没有任何候选时返回 (None, [])。
    """
    if not candidates:
        return None, []
    return candidates[0], list(candidates[1:])


def insert_images(text: str, images: list[dict]) -> str:
    """把图片作为独立段落插入 Markdown 正文，按段落均匀分布。

    规则：
      - 以空行分块；代码围栏块整体跳过（不在代码块前后插图）；
      - 图片插在第 k*(n+1) 段之后（k=1..n），即把正文均分为 n+1 份；
      - 幂等：图片 URL 已出现在正文里就跳过，重跑不会重复插入。
    """
    if not text or not text.strip() or not images:
        return text
    # 幂等过滤：已在正文里的图不再插入
    todo = [img for img in images if img.get("img_url") and img["img_url"] not in text]
    if not todo:
        return text

    blocks = text.split("\n\n")
    in_code = False
    eligible: list[int] = []       # 可插图位置（块序号，插在该块之后）
    for idx, block in enumerate(blocks):
        stripped = block.lstrip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if not in_code and stripped:
            eligible.append(idx)

    n = len(todo)
    if not eligible:
        return text
    total = len(eligible)
    # 插入点：第 i 张图插在 eligible 的 (i+1)*total/(n+1) 处，向前取整并去重
    positions = sorted({
        eligible[min(total, max(1, ((i + 1) * total) // (n + 1))) - 1]
        for i in range(n)
    })
    insert_at: dict[int, list[dict]] = {}
    for i, img in enumerate(todo[:len(positions)]):
        insert_at.setdefault(positions[i], []).append(img)

    out: list[str] = []
    for idx, block in enumerate(blocks):
        out.append(block)
        for img in insert_at.get(idx, ()):
            out.append(f"![{img.get('alt', '')}]({img['img_url']})")
    return "\n\n".join(out)


def illustrate_state(state: dict, images: list, thumbnails: list[str] | None = None) -> dict:
    """对工作流最终 state 做配图后处理，返回新 state（不改入参）。

    新增 cover_image（/images/... 绝对路径，无候选时为空串）；
    final_article 与 multi_platform 的文章类字段注入正文插图。
    """
    candidates = normalize_candidates(images, thumbnails)
    cover, inline = pick_cover(candidates)
    inline = inline[:MAX_INLINE_IMAGES]
    result = dict(state or {})
    result["cover_image"] = cover["img_url"] if cover else ""
    if not inline:
        return result

    final_text = str(result.get("final_article") or "")
    if final_text.strip():
        result["final_article"] = insert_images(final_text, inline)

    multi = result.get("multi_platform")
    if isinstance(multi, dict) and multi:
        patched = dict(multi)
        for key in ARTICLE_PLATFORM_KEYS:
            value = patched.get(key)
            if isinstance(value, str) and value.strip():
                patched[key] = insert_images(value, inline)
        result["multi_platform"] = patched

    logger.info(f"[illustrate] 配图完成：封面 {result['cover_image'] or '无'}，"
                f"正文插图 {min(len(inline), MAX_INLINE_IMAGES)} 张")
    return result
