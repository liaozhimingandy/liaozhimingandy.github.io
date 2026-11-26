"""热点 topic 的单次聚类处理。

只做一次扫描：把 pending 且未绑定 event 的 topic 合并到已有 event，
或创建新 event。数据读写走 session_scope + TopicDAO/EventDAO/NewsDAO/RelDAO，
每个 topic 的合并/新建在同一会话事务内，单条失败不影响其余 topic。

调度：由 scheduler.py 定时触发（run_cluster_now / cluster loop），
也可手动运行：py -3.13 -m app.article.cluster
"""

import asyncio
import hashlib
import json
import re
from collections import Counter

from sqlmodel.ext.asyncio.session import AsyncSession

from ..core import session_scope
from .dal import EventDAO, NewsDAO, RelDAO, TopicDAO
from .models import ArticleEvent
from .utils import normalize_news_url

try:
    import jieba
except Exception:  # jieba 异常时退化为正则分词
    jieba = None

try:
    import numpy as np
except Exception:  # numpy 缺失时禁用 embedding 精判，只用 SimHash
    np = None

try:
    from simhash import Simhash as _ExternalSimhash
except Exception:
    _ExternalSimhash = None
_EXTERNAL_SIMHASH_FAILED = False

SIMHASH_FAST_MATCH = 3
SIMHASH_SKIP = 8
EMBED_THRESHOLD = 0.75

EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
_MASK64 = (1 << 64) - 1

# 全局只加载一次；加载失败也只尝试一次，避免每条 topic 重复报错
_MODEL = None
_MODEL_UNAVAILABLE = False


def _get_model():
    global _MODEL, _MODEL_UNAVAILABLE
    if _MODEL is not None:
        return _MODEL
    if _MODEL_UNAVAILABLE:
        return None
    try:
        from sentence_transformers import SentenceTransformer

        _MODEL = SentenceTransformer(EMBED_MODEL_NAME)
        print(f"[cluster] 已加载向量模型：{EMBED_MODEL_NAME}")
        return _MODEL
    except Exception as exc:
        _MODEL_UNAVAILABLE = True
        print(f"[cluster] 向量模型不可用，后续只用 SimHash：{type(exc).__name__}: {exc}")
        return None


def _tokens(text: str):
    """中文标题用字二元组，短标题近重复时 SimHash 比整词更稳定。"""
    text = str(text or "").strip()
    if not text:
        return []
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", text))
    tokens = [chinese[index:index + 2] for index in range(len(chinese) - 1)]
    tokens.extend(re.findall(r"[A-Za-z0-9]+", text.lower()))
    if tokens:
        return tokens
    if jieba is not None:
        try:
            return [word.strip() for word in jieba.lcut(text) if word.strip()]
        except Exception:
            pass
    return re.findall(r"[\u4e00-\u9fff]+|[A-Za-z0-9]+", text)


def _simhash_value(text: str) -> int:
    """优先用 simhash 包；不可用时用 64 位 md5 加权 fallback。"""
    global _EXTERNAL_SIMHASH_FAILED
    tokens = _tokens(text)
    if not tokens:
        return 0

    if _ExternalSimhash is not None and not _EXTERNAL_SIMHASH_FAILED:
        try:
            return int(_ExternalSimhash(" ".join(tokens)).value) & _MASK64
        except Exception as exc:
            _EXTERNAL_SIMHASH_FAILED = True
            print(f"[cluster] simhash 包调用失败，改用内置实现：{type(exc).__name__}: {exc}")

    vector = [0] * 64
    for token, weight in Counter(tokens).items():
        digest = hashlib.md5(token.encode("utf-8")).digest()
        value = int.from_bytes(digest[:8], "big")
        for index in range(64):
            vector[index] += weight if (value >> index) & 1 else -weight
    result = 0
    for index, weight in enumerate(vector):
        if weight > 0:
            result |= 1 << index
    return result & _MASK64


def _parse_stored_simhash(raw) -> int | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return int(text, 10) & _MASK64
    except ValueError:
        try:
            return int(text, 16) & _MASK64
        except ValueError:
            return None


def _hamming(left: int, right: int) -> int:
    return ((int(left) & _MASK64) ^ (int(right) & _MASK64)).bit_count()


def _encode(text: str):
    if np is None:
        return None
    model = _get_model()
    if model is None:
        return None
    try:
        vector = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
    except TypeError:
        # 旧版 sentence-transformers 不支持 normalize_embeddings 参数
        try:
            vector = model.encode(text, convert_to_numpy=True)
        except Exception as exc:
            print(f"[cluster] 向量编码失败：{type(exc).__name__}: {exc}")
            return None
    except Exception as exc:
        print(f"[cluster] 向量编码失败：{type(exc).__name__}: {exc}")
        return None
    try:
        array = np.asarray(vector, dtype=float).reshape(-1)
        norm = float(np.linalg.norm(array))
        if norm > 0:
            array = array / norm
        return array
    except Exception as exc:
        print(f"[cluster] 向量格式化失败：{type(exc).__name__}: {exc}")
        return None


def _load_embedding(raw):
    if np is None or raw is None:
        return None
    try:
        payload = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        array = np.asarray(payload, dtype=float).reshape(-1)
        if array.size == 0:
            return None
        norm = float(np.linalg.norm(array))
        return array / norm if norm > 0 else None
    except Exception:
        return None


def _cosine(left, right) -> float:
    if np is None:
        return 0.0
    norm = float(np.linalg.norm(left) * np.linalg.norm(right))
    if norm <= 0:
        return 0.0
    return float(np.dot(left, right) / norm)


async def _event_similarity(dao: EventDAO, event: ArticleEvent, topic_title: str):
    """计算 topic 与 event 的余弦相似度；缺向量时生成并回写 event_embedding。"""
    vector = _load_embedding(event.event_embedding)
    if vector is None:
        if event.event_embedding:
            print(f"[cluster] event#{event.id} 向量解析失败，尝试重建")
        base = str(event.event_summary or event.event_title or "").strip()
        if not base:
            print(f"[cluster] event#{event.id} 无标题/摘要，无法生成向量")
            return None
        vector = _encode(base)
        if vector is None:
            print(f"[cluster] event#{event.id} 向量生成失败，降级只用 SimHash")
            return None
        if await dao.update_embedding(int(event.id or 0), vector.tolist()):
            event.event_embedding = vector.tolist()
        else:
            print(f"[cluster] event#{event.id} 向量回写失败")

    topic_vector = _encode(topic_title)
    if topic_vector is None:
        print(f"[cluster] topic 向量生成失败，降级只用 SimHash：{topic_title}")
        return None
    return _cosine(vector, topic_vector)


def _log_compare(topic_title: str, event: ArticleEvent, dist: int, cosine, result: str):
    cos_text = "-" if cosine is None else f"{cosine:.4f}"
    print(
        f"[cluster] topic《{topic_title}》 vs event#{event.id}"
        f"《{event.event_title}》 | 海明={dist} | 余弦={cos_text} | {result}"
    )


def _json_list(raw):
    """安全解析 JSON 数组字段；异常或非数组都返回空列表。"""
    if raw is None:
        return []
    try:
        payload = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        return payload if isinstance(payload, list) else []
    except Exception:
        return []


def _compact_text(value, limit: int = 220) -> str:
    text = str(value or "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _build_event_summary(rows, old_summary="") -> str:
    """用新闻标题 + 正文开头生成简短摘要，不依赖外部模型。"""
    titles = []
    snippets = []
    for row in rows:
        title = _compact_text(row.title, 120)
        if title and "appkey" not in title.lower() and title not in titles:
            titles.append(title)
        text = _compact_text(row.text, 220)
        lowered = text.lower()
        if (
            len(text) >= 20
            and not lowered.startswith(("appkey", "var ", "function", "{"))
            and text not in snippets
        ):
            snippets.append(text)
    parts = []
    if titles:
        parts.append("；".join(titles[:3]))
    if snippets:
        parts.append(snippets[0])
    if not parts:
        return str(old_summary or "")
    return "。".join(parts)[:500]


async def _recompute_all_event_simhash(dao: EventDAO, events: list[ArticleEvent]) -> int:
    """按当前解释器可用的 SimHash 实现重算全部 event，避免跨环境哈希不一致。"""
    pairs = []
    for event in events:
        value = str(_simhash_value(event.event_title or ""))
        if str(event.simhash or "") != value:
            pairs.append((int(event.id or 0), value))
            event.simhash = value
    changed = await dao.update_simhashes(pairs)
    print(f"[cluster] event simhash 重算：{changed}/{len(events)} 条更新")
    return changed


async def _refresh_event_material(session: AsyncSession,
                                  event_id: int, event_title: str) -> bool:
    """把新闻链接、图片、摘要和 event_news_rel 回填到单个 event。"""
    events = EventDAO(session)
    event = await events.get_by_id(event_id)
    if event is None:
        return False

    news_rows = await NewsDAO(session).list_for_event(event_id, event_title)
    source_urls = []
    seen_urls = set()
    images = []
    seen_images = set()
    for row in news_rows:
        url = str(row.news_url or "").strip()
        if url:
            key = normalize_news_url(url) or url
            if key not in seen_urls:
                seen_urls.add(key)
                source_urls.append(url)
        for item in row.images or []:
            if not isinstance(item, dict):
                continue
            img_url = str(item.get("img_url") or "").strip()
            if not img_url or img_url in seen_images:
                continue
            seen_images.add(img_url)
            images.append({"img_url": img_url, "alt": str(item.get("alt") or "")})

    summary = _build_event_summary(news_rows, str(event.event_summary or ""))
    if not summary and event_title:
        # 没有采集到新闻时，至少用事件标题作为最小摘要
        summary = _compact_text(event_title, 200)

    changed = (
        summary != str(event.event_summary or "")
        or source_urls != [str(u) for u in (event.source_urls or [])]
        or images != [dict(i) for i in (event.images or []) if isinstance(i, dict)]
    )
    if changed or news_rows:
        # 直接改托管实体属性，flush 随 commit 生效；关联单独绑定
        event.event_summary = summary or None
        event.source_urls = source_urls
        event.images = images
        await RelDAO(session).link(event_id, [int(row.id or 0) for row in news_rows])
        await session.commit()
        print(
            f"[cluster] event#{event_id}《{event_title}》素材：新闻 {len(news_rows)} 条，"
            f"链接 {len(source_urls)}，图片 {len(images)}"
        )
    return bool(changed or news_rows)


async def _refresh_all_event_materials(session: AsyncSession) -> int:
    """兜底刷新所有 event，保证历史聚类的空字段也能补上。"""
    events = await EventDAO(session).list_all(limit=10000)
    changed = 0
    for event in events:
        try:
            if await _refresh_event_material(
                    session, int(event.id or 0), event.event_title):
                changed += 1
        except Exception as exc:
            print(f"[cluster] event#{event.id} 素材刷新失败：{type(exc).__name__}: {exc}")
    print(f"[cluster] event 素材刷新完成：{changed}/{len(events)} 条有更新")
    return changed


async def cluster_new_topics() -> None:
    """单次聚类：pending topic 合并进已有 event 或新建 event；无返回值。

    全程一个会话（session_scope 自动提交），每个 topic 处理后增量提交，
    单条失败回滚该 topic 的写入后继续。
    """
    async with session_scope() as session:
        topics_dao = TopicDAO(session)
        events_dao = EventDAO(session)

        topics = await topics_dao.list_pending()
        events = await events_dao.list_for_cluster()
        print(f"[cluster] 待处理 topic {len(topics)} 条，已有 event {len(events)} 条")
        await _recompute_all_event_simhash(events_dao, events)
        await session.commit()

        if not topics:
            await _refresh_all_event_materials(session)
            print("[cluster] 单次聚类完成")
            return

        for topic in topics:
            topic_id = int(topic.id or 0)
            title = str(topic.title or "").strip()
            if not title:
                continue
            hot_score = int(topic.hot_score or 0)

            try:
                topic_hash = _simhash_value(title)
                matched_event = None
                matched_dist = None
                matched_cosine = None

                for event in events:
                    event_hash = _parse_stored_simhash(event.simhash)
                    if event_hash is None:
                        print(f"[cluster] event#{event.id} simhash 无效，跳过")
                        continue
                    dist = _hamming(topic_hash, event_hash)

                    if dist <= SIMHASH_FAST_MATCH:
                        matched_event = event
                        matched_dist = dist
                        _log_compare(title, event, dist, None, "SimHash 快速匹配")
                        break

                    if dist >= SIMHASH_SKIP:
                        _log_compare(title, event, dist, None, "海明距离过大，跳过")
                        continue

                    cosine = await _event_similarity(events_dao, event, title)
                    if cosine is None:
                        _log_compare(title, event, dist, None, "向量不可用，跳过")
                        continue
                    if cosine >= EMBED_THRESHOLD:
                        matched_event = event
                        matched_dist = dist
                        matched_cosine = cosine
                        _log_compare(title, event, dist, cosine, "向量精判匹配")
                        break
                    _log_compare(title, event, dist, cosine, "向量相似度不足")

                if matched_event is not None:
                    await events_dao.merge_topic(
                        topic_id, int(matched_event.id or 0), hot_score)
                    cos_text = (
                        "快速匹配" if matched_cosine is None else f"余弦={matched_cosine:.4f}"
                    )
                    print(
                        f"[cluster] 合并成功：topic#{topic_id}《{title}》 -> "
                        f"event#{matched_event.id}（海明={matched_dist}，{cos_text}）"
                    )
                else:
                    topic_vector = _encode(title)
                    embedding = topic_vector.tolist() if topic_vector is not None else None

                    new_event = await events_dao.create_for_topic(
                        topic_id, title, hot_score, str(topic_hash), embedding,
                    )
                    events.append(new_event)
                    print(
                        f"[cluster] 新建 event#{new_event.id}《{title}》"
                        f" <- topic#{topic_id}，simhash={topic_hash}"
                    )
                await session.commit()
            except Exception as exc:
                await session.rollback()
                print(f"[cluster] topic#{topic_id}《{title}》处理失败，已跳过：{exc}")

        # 历史 event 也可能没有素材字段，统一兜底回填一次
        await _refresh_all_event_materials(session)
        print("[cluster] 单次聚类完成")


if __name__ == "__main__":
    asyncio.run(cluster_new_topics())
