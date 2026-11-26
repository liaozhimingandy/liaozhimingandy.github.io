"""article 各表 DAO：通用 CRUD 复用 BaseDAO，专用查询放这里。

分层位置：Service / collector / cluster → 本文件 DAO → SQLModel → DB

约定：
    - 所有写操作只 flush 不 commit，事务边界在 service / session_scope；
    - 跨方言兼容：Postgres（生产）与 SQLite 内存库（测试）都能执行，
      不使用 JSONB 专有函数（如 jsonb_array_length），数组过滤在 Python 侧完成；
    - 唯一约束冲突用先查后插策略（SQLAlchemy 2.1 起 flush 冲突会使
      整个会话事务待回滚，SAVEPOINT 不再适用）。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from .base import BaseDAO
from ..models import (
    Article,
    ArticleEvent,
    ArticleEventNewsRel,
    ArticleNews,
    ArticleTopic,
    utcnow,
)
from ..utils import normalize_news_url


def _log(message: str) -> None:
    print(f"[article-dal] {message}")


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- #
# topic（热搜采集阶段）
# --------------------------------------------------------------------------- #

class TopicDAO(BaseDAO[ArticleTopic]):
    model = ArticleTopic

    async def save_topics(self, items: list[dict]) -> int:
        """热搜批量入库（title+source 去重），返回新增条数。

        跨方言实现：先查已存在的 (title, source) 对，只插缺失项；
        每轮最多几十条，逐条判断的开销可忽略。
        """
        rows: list[dict] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            rows.append({
                "title": title,
                "source": str(item.get("source") or "").strip(),
                "hot_score": _to_int(item.get("hot_score")),
            })
        if not rows:
            return 0

        existing = {
            (t.title, t.source)
            for t in (await self._execute(select(ArticleTopic), "save_topics.scan")).all()
        }
        # 批内同样按 (title, source) 去重，避免同批重复项触发唯一约束
        seen: set[tuple[str, str]] = set()
        fresh: list[dict] = []
        for r in rows:
            key = (r["title"], r["source"])
            if key in existing or key in seen:
                continue
            seen.add(key)
            fresh.append(r)
        if not fresh:
            return 0
        await self.bulk_create([ArticleTopic(**r) for r in fresh])
        return len(fresh)

    async def list_pending(self) -> list[ArticleTopic]:
        """待聚类 topic：event_id 为空且 status=pending，按 id 顺序。"""
        stmt = (
            select(ArticleTopic)
            .where(ArticleTopic.event_id.is_(None), ArticleTopic.status == "pending")
            .order_by(ArticleTopic.id)
        )
        return list((await self._execute(stmt, "list_pending")).all())

    async def count_pending(self) -> int:
        stmt = (
            select(ArticleTopic.id)
            .where(ArticleTopic.event_id.is_(None), ArticleTopic.status == "pending")
        )
        result = await self._execute(stmt, "count_pending")
        return len(result.all())

    async def mark_merged(self, topic_id: int, event_id: int) -> bool:
        """topic 绑定 event 并标记 merged。"""
        result = await self.exec_write(
            ArticleTopic.__table__.update()
            .where(ArticleTopic.id == topic_id)
            .values(event_id=event_id, status="merged"),
            "mark_merged",
        )
        return bool(result.rowcount)


# --------------------------------------------------------------------------- #
# event（聚类阶段）
# --------------------------------------------------------------------------- #

class EventDAO(BaseDAO[ArticleEvent]):
    model = ArticleEvent

    async def list_for_cluster(self) -> list[ArticleEvent]:
        """聚类用：全部事件（需 simhash 与 embedding），按 id 顺序。"""
        return list((await self._execute(
            select(ArticleEvent).order_by(ArticleEvent.id), "list_for_cluster",
        )).all())

    async def update_simhashes(self, pairs: list[tuple[int, str]]) -> int:
        """批量回写 event simhash，返回更新条数。"""
        if not pairs:
            return 0
        updated = 0
        for event_id, value in pairs:
            result = await self.exec_write(
                ArticleEvent.__table__.update()
                .where(ArticleEvent.id == event_id)
                .values(simhash=value),
                "update_simhashes",
            )
            updated += int(result.rowcount or 0)
        return updated

    async def update_embedding(self, event_id: int, vector: list[float]) -> bool:
        """回写 event 向量（JSON 列，跨方言）。"""
        result = await self.exec_write(
            ArticleEvent.__table__.update()
            .where(ArticleEvent.id == event_id)
            .values(event_embedding=vector),
            "update_embedding",
        )
        return bool(result.rowcount)

    async def merge_topic(self, topic_id: int, event_id: int, hot_score: int) -> bool:
        """event 累计得分 + topic 标记 merged（同一会话事务，由上层提交）。"""
        await self.exec_write(
            ArticleEvent.__table__.update()
            .where(ArticleEvent.id == event_id)
            .values(
                total_score=ArticleEvent.total_score + hot_score,
                score_gain=ArticleEvent.score_gain + hot_score,
                last_seen=utcnow(),
            ),
            "merge_topic.score",
        )
        return await TopicDAO(self.session).mark_merged(topic_id, event_id)

    async def create_for_topic(self, topic_id: int, title: str, hot_score: int,
                               simhash: str, embedding: list[float] | None) -> ArticleEvent:
        """新建 event 并把 topic 标记 merged；flush 回填 id，提交由上层负责。"""
        event = ArticleEvent(
            event_title=title,
            total_score=hot_score,
            score_gain=hot_score,
            simhash=simhash,
            event_embedding=embedding,
        )
        await self.create(event)
        await TopicDAO(self.session).mark_merged(topic_id, int(event.id or 0))
        return event

    async def list_all(self, limit: int = 100) -> list[ArticleEvent]:
        """全部事件（管理端回看），按 last_seen 倒序。"""
        stmt = (
            select(ArticleEvent)
            .order_by(ArticleEvent.last_seen.desc(), ArticleEvent.id.desc())
            .limit(max(_to_int(limit), 0))
        )
        return list((await self._execute(stmt, "list_all")).all())

    async def list_pending_materialized(self, limit: int | None = None) -> list[ArticleEvent]:
        """可生成事件：pending 且已有素材链接，按热度排序。

        素材是否就位（source_urls 非空）在 Python 侧过滤，
        不依赖 JSONB 专有函数，Postgres / SQLite 通用。
        """
        stmt = (
            select(ArticleEvent)
            .where(ArticleEvent.status == "pending")
            .order_by(ArticleEvent.total_score.desc(), ArticleEvent.id.asc())
        )
        candidates = list((await self._execute(stmt, "list_pending_materialized")).all())
        ready = [e for e in candidates if e.source_urls]
        if limit:
            ready = ready[: max(_to_int(limit), 0)]
        return ready

    async def mark_status(self, event_id: int, status: str) -> bool:
        """更新 event.status（drafted/review/done/reject 等），同步刷新 last_seen。"""
        result = await self.exec_write(
            ArticleEvent.__table__.update()
            .where(ArticleEvent.id == event_id)
            .values(status=str(status or "").strip(), last_seen=utcnow()),
            "mark_status",
        )
        if not result.rowcount:
            _log(f"event 不存在，未更新状态：event={event_id}")
        return bool(result.rowcount)


# --------------------------------------------------------------------------- #
# news（采集素材）
# --------------------------------------------------------------------------- #

class NewsDAO(BaseDAO[ArticleNews]):
    model = ArticleNews

    async def is_collected(self, url: str) -> bool:
        """按规范化 url_key / 原始链接判断新闻是否已入库。"""
        raw = str(url or "").strip()
        key = normalize_news_url(raw)
        if not raw and not key:
            return False
        conditions = []
        if key:
            conditions.append(ArticleNews.url_key == key)
        if raw:
            conditions.append(ArticleNews.news_url == raw)
        result = await self._execute(
            select(ArticleNews.id).where(or_(*conditions)).limit(1), "is_collected",
        )
        return result.first() is not None

    async def insert_news(self, art: dict) -> bool:
        """新闻素材入库（规范化链接去重）；True=本次真正插入。

        先查后插（与 save_topics 同策略）：SQLAlchemy 2.1 起 flush 冲突
        会将整个会话事务置为待回滚（PendingRollbackError），SAVEPOINT
        无法再隔离唯一约束冲突，故改为 SELECT 预判后插入。
        同一采集批次内同一链接只入一条；并发采集由外部循环保证单写者。
        """
        if not isinstance(art, dict):
            return False
        url = str(art.get("url") or "").strip()
        if not url:
            _log("insert_news 缺少 url，忽略")
            return False

        if await self.is_collected(url):
            _log(f"news 已存在，跳过：{url[:80]}")
            return False

        images = [
            {"img_url": str(img.get("img_url") or "").strip(),
             "alt": str(img.get("alt") or "")}
            for img in (art.get("images") or [])
            if isinstance(img, dict) and str(img.get("img_url") or "").strip()
        ]
        news = ArticleNews(
            hot_topic=str(art.get("hot_topic") or "").strip() or None,
            hot_source=str(art.get("hot_source") or "").strip() or None,
            hot_score=_to_int(art.get("hot_score")),
            news_url=url,
            url_key=normalize_news_url(url),
            title=str(art.get("title") or "").strip() or None,
            author=str(art.get("author") or "").strip() or None,
            pub_date=str(art.get("date") or "").strip() or None,
            text=str(art.get("text") or ""),
            images=images,
            thumbnail=str(art.get("thumbnail") or "").strip() or None,
        )
        self.session.add(news)
        try:
            await self.session.flush()
        except IntegrityError:
            # 理论竞态兜底：预查与插入间被并发写入时，回滚并跳过
            await self.session.rollback()
            _log(f"news 并发冲突，跳过：{url[:80]}")
            return False
        _log(f"news 入库成功：{url[:80]}（图片 {len(images)} 张）")
        return True

    async def list_for_event(self, event_id: int, event_title: str) -> list[ArticleNews]:
        """event 对应 topic 下采集到的新闻（topic 标题命中或事件标题兜底）。"""
        topic_titles = (
            select(ArticleTopic.title)
            .where(ArticleTopic.event_id == event_id)
        )
        conditions = [ArticleNews.hot_topic.in_(topic_titles)]
        title = str(event_title or "").strip()
        if title:
            conditions.append(ArticleNews.hot_topic == title)
        stmt = (
            select(ArticleNews)
            .where(or_(*conditions))
            .order_by(ArticleNews.id)
        )
        return list((await self._execute(stmt, "list_for_event")).all())

    async def list_by_rel(self, event_id: int) -> list[ArticleNews]:
        """event 已绑定关联的新闻（article_event_news_rel join）。"""
        stmt = (
            select(ArticleNews)
            .join(ArticleEventNewsRel, ArticleEventNewsRel.news_id == ArticleNews.id)
            .where(ArticleEventNewsRel.event_id == event_id)
            .order_by(ArticleNews.id)
        )
        return list((await self._execute(stmt, "list_by_rel")).all())


# --------------------------------------------------------------------------- #
# event-news 关联
# --------------------------------------------------------------------------- #

class RelDAO(BaseDAO[ArticleEventNewsRel]):
    model = ArticleEventNewsRel

    async def link(self, event_id: int, news_ids: list[int]) -> int:
        """绑定关联；已存在的 (event_id, news_id) 跳过。返回新增关联数。"""
        ids = [nid for nid in news_ids if nid]
        if not ids:
            return 0
        existing = {
            rel.news_id
            for rel in (await self._execute(
                select(ArticleEventNewsRel)
                .where(ArticleEventNewsRel.event_id == event_id), "link.scan",
            )).all()
        }
        fresh = [ArticleEventNewsRel(event_id=event_id, news_id=nid)
                 for nid in ids if nid not in existing]
        if fresh:
            await self.bulk_create(fresh)
        return len(fresh)


# --------------------------------------------------------------------------- #
# article（生成结果）
# --------------------------------------------------------------------------- #

# 列表接口需要返回的字段（不含 outline/draft 等正文大字段）
_ARTICLE_BRIEF_COLUMNS = (
    Article.id, Article.uuid, Article.event_id, Article.event_title,
    Article.images, Article.source_urls, Article.model, Article.status,
    Article.is_current, Article.thread_id, Article.create_time, Article.update_time,
)


class ArticleDAO(BaseDAO[Article]):
    model = Article

    async def save_new_version(self, data: dict) -> int:
        """保存生成结果（同 event 旧版本置为非当前）；返回新文章 id。

        事务边界：两个写操作在同一会话，由上层统一 commit。
        """
        if not isinstance(data, dict):
            return 0
        try:
            event_id = int(data.get("event_id"))
        except (TypeError, ValueError):
            _log("save_new_version 缺少合法 event_id，忽略")
            return 0

        await self.exec_write(
            Article.__table__.update()
            .where(Article.event_id == event_id)
            .values(is_current=False),
            "save_new_version.deprecate",
        )
        article = Article(
            event_id=event_id,
            event_title=str(data.get("event_title") or "").strip() or None,
            outline=str(data.get("outline") or ""),
            draft=str(data.get("draft") or ""),
            multi_platform=data.get("multi_platform") or {},
            check_report=str(data.get("check_report") or ""),
            final_article=str(data.get("final_article") or ""),
            images=data.get("images") or [],
            source_urls=data.get("source_urls") or [],
            model=str(data.get("model") or ""),
            status=str(data.get("status") or "drafted"),
            thread_id=str(data.get("thread_id") or "") or None,
            uuid=str(data.get("uuid") or "").strip(),
        )
        await self.create(article)
        _log(f"article 保存成功：id={article.id}, event={event_id}")
        return int(article.id or 0)

    async def list_articles(self, event_id: int | None = None, limit: int = 20,
                            include_history: bool = False) -> list[Article]:
        """文章列表（不含正文大字段），按 id 倒序；默认只看当前版本。"""
        stmt = select(*_ARTICLE_BRIEF_COLUMNS)
        conditions = []
        if event_id is not None:
            conditions.append(Article.event_id == event_id)
        if not include_history:
            conditions.append(Article.is_current.is_(True))
        if conditions:
            stmt = stmt.where(*conditions)
        stmt = stmt.order_by(Article.id.desc()).limit(max(_to_int(limit), 0))
        rows = (await self._execute(stmt, "list_articles")).all()
        return [Article(**dict(row._mapping)) for row in rows]

    async def get_by_uuid(self, article_uuid: str) -> Article | None:
        raw = str(article_uuid or "").strip()
        if not raw:
            return None
        result = await self._execute(
            select(Article).where(Article.uuid == raw).limit(1), "get_by_uuid",
        )
        return result.first()
