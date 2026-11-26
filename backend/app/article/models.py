"""article 领域模型：SQLModel 表模型 + 非表 Pydantic 模型。

表模型（table=True）遵循 FastAPI/SQLModel 官方惯例：
    - 建表由 core/database.init_db() 的 SQLModel.metadata.create_all 完成，
      不维护 DDL 文件；create_all 只建不存在的表，不改已有表结构；
    - 字段名与线上已迁移的 article_* 五张表保持一致（Postgres 表已存在，
      create_all 对它们是 no-op，两侧结构同源）；
    - JSON 字段用通用 JSON 列类型：Postgres 上落在 JSONB，SQLite（内存库/测试）
      落在 JSON，读写行为一致。

非表模型：GenerationTask / CollectStats / EventMaterial（运行时状态与组合视图）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, NaiveDatetime
from sqlalchemy import JSON, Column, Text, UniqueConstraint
from sqlmodel import SQLModel, Field


def utcnow() -> datetime:
    """统一 UTC 时间（naive UTC；配合 NaiveDatetime 注解声明 naive 存储）。

    SQLModel 0.0.50 起 datetime 字段默认按 UTCDateTime 处理并要求 aware 值；
    article_* 表列历史语义为 naive UTC，故显式标注 NaiveDatetime 保持不变。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------------- #
# 表模型（article_topic / article_event / article_news / article_event_news_rel / article）
# --------------------------------------------------------------------------- #

class ArticleTopic(SQLModel, table=True):
    """原始热搜条目（article_topic）。同一来源同一标题唯一。"""

    __tablename__ = "article_topic"
    __table_args__ = (
        UniqueConstraint("title", "source", name="ux_article_topic_title_source"),
    )

    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(default="", index=True)
    source: str = Field(default="")
    hot_score: int = Field(default=0)
    fetch_time: NaiveDatetime | None = Field(default_factory=utcnow)
    status: str = Field(default="pending", index=True)
    event_id: int | None = Field(default=None, index=True)


class ArticleEvent(SQLModel, table=True):
    """聚合事件（article_event）：聚类输出，也是用户可选择的“话题”。"""

    __tablename__ = "article_event"

    id: int | None = Field(default=None, primary_key=True)
    event_title: str = Field(default="", index=True)
    event_summary: str | None = None
    total_score: int = Field(default=0)
    score_gain: int = Field(default=0)
    first_seen: NaiveDatetime | None = Field(default_factory=utcnow)
    last_seen: NaiveDatetime | None = Field(default_factory=utcnow)
    status: str = Field(default="pending", index=True)
    source_urls: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    images: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    simhash: str = Field(default="")
    remark: str | None = None
    event_embedding: list[float] | None = Field(default=None, sa_column=Column(JSON))


class ArticleNews(SQLModel, table=True):
    """采集入库的新闻素材（article_news）。url_key / news_url 双唯一去重。"""

    __tablename__ = "article_news"
    __table_args__ = (
        UniqueConstraint("url_key", name="ux_article_news_url_key"),
        UniqueConstraint("news_url", name="ux_article_news_url"),
    )

    id: int | None = Field(default=None, primary_key=True)
    hot_topic: str | None = None
    hot_source: str | None = None
    hot_score: int = Field(default=0)
    news_url: str = Field(default="")
    url_key: str = Field(default="", index=True)
    title: str | None = None
    author: str | None = None
    pub_date: str | None = None
    text: str = Field(default="", sa_column=Column(Text))
    images: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    thumbnail: str | None = None
    create_time: NaiveDatetime | None = Field(default_factory=utcnow)


class ArticleEventNewsRel(SQLModel, table=True):
    """event-news 多对多关联（article_event_news_rel）。"""

    __tablename__ = "article_event_news_rel"

    event_id: int = Field(primary_key=True)
    news_id: int = Field(primary_key=True)


class Article(SQLModel, table=True):
    """LLM 生成的文章（article 表，同一 event 保留历史版本）。"""

    __tablename__ = "article"
    __table_args__ = (
        UniqueConstraint("uuid", name="ux_article_uuid"),
    )

    id: int | None = Field(default=None, primary_key=True)
    event_id: int = Field(default=0, index=True)
    event_title: str | None = None
    outline: str = Field(default="", sa_column=Column(Text))
    draft: str = Field(default="", sa_column=Column(Text))
    multi_platform: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON))
    check_report: str = Field(default="", sa_column=Column(Text))
    final_article: str = Field(default="", sa_column=Column(Text))
    images: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    source_urls: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    model: str = Field(default="")
    status: str = Field(default="drafted")
    is_current: bool = Field(default=True)
    thread_id: str | None = None
    uuid: str = Field(default="")
    create_time: NaiveDatetime | None = Field(default_factory=utcnow)
    update_time: NaiveDatetime | None = Field(default_factory=utcnow)


# --------------------------------------------------------------------------- #
# 非表模型（运行时状态与组合视图）
# --------------------------------------------------------------------------- #

class EventMaterial(BaseModel):
    """生成素材：事件本体 + 已截断的正文素材列表（组合视图，不入库）。"""

    id: int
    event_title: str = ""
    event_summary: str | None = None
    status: str = "pending"
    total_score: int = 0
    source_urls: list[str] = Field(default_factory=list)
    images: list[dict[str, Any]] = Field(default_factory=list)
    source_contents: list[str] = Field(default_factory=list)

    @classmethod
    def from_event(cls, event: ArticleEvent) -> "EventMaterial":
        return cls(
            id=int(event.id or 0),
            event_title=event.event_title,
            event_summary=event.event_summary,
            status=event.status,
            total_score=event.total_score,
            source_urls=[str(u) for u in (event.source_urls or [])],
            images=[dict(i) for i in (event.images or []) if isinstance(i, dict)],
        )


class GenerationTask(BaseModel):
    """一次文章生成任务的运行时状态（内存登记，不入库）。"""

    task_id: str
    event_id: int
    event_title: str = ""
    status: str = "queued"          # queued / running / done / failed
    error: str = ""
    thread_id: str = ""
    article_id: int = 0
    article_uuid: str = ""
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""


class CollectStats(BaseModel):
    """一轮采集的统计。"""

    topics: int = 0
    articles: int = 0
    skipped: int = 0
    error: str = ""
