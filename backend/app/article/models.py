"""article 领域模型：SQLModel 表模型 + 非表 Pydantic 模型。

表模型（table=True）遵循 FastAPI/SQLModel 官方惯例：
    - 建表由 core/database.init_db() 的 SQLModel.metadata.create_all 完成，
      不维护 DDL 文件；create_all 只建不存在的表，不改已有表结构；
    - 字段名与线上已迁移的 article_* 五张表保持一致（Postgres 表已存在，
      create_all 对它们是 no-op，两侧结构同源）；
    - JSON 字段用通用 JSON 列类型：Postgres 上落在 JSONB，SQLite（内存库/测试）
      落在 JSON，读写行为一致。

非表模型：CollectStats / EventMaterial（运行时组合视图）。

GenerationTask 已升级为表模型 article_generation_task：任务状态入库，
前端轮询查表即可，进程重启不丢、多实例可见；LangGraph 断点靠 thread_id
从 checkpointer 恢复，运行上下文凭 event_id 重读素材重建。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel
from sqlalchemy import JSON, Column, Text, UniqueConstraint
from sqlmodel import SQLModel, Field


def utcnow() -> datetime:
    """统一 UTC 时间（timezone-aware，自带 +00:00 时区标记）。

    历史上这里存 naive UTC，DB 里比北京时间少 8 小时又没有时区标记，
    排查问题时极易误读；现改为 aware UTC，新表列直接建为带时区类型，
    存量 Postgres 列由启动时的时间列迁移（migrate_time_columns）升级。
    """
    return datetime.now(timezone.utc)


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
    fetch_time: datetime | None = Field(default_factory=utcnow)
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
    first_seen: datetime | None = Field(default_factory=utcnow)
    last_seen: datetime | None = Field(default_factory=utcnow)
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
    create_time: datetime | None = Field(default_factory=utcnow)


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
    # 封面图（/images/... 站点根路径；illustrate 落库前从素材图选出）
    cover_image: str = Field(default="", sa_column=Column(Text))
    images: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    source_urls: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    model: str = Field(default="")
    status: str = Field(default="drafted")
    is_current: bool = Field(default=True)
    thread_id: str | None = None
    uuid: str = Field(default="")
    create_time: datetime | None = Field(default_factory=utcnow)
    update_time: datetime | None = Field(default_factory=utcnow)


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
    # 各篇新闻的封面缩略图（news.thumbnail，本地相对路径），作封面兜底候选
    thumbnails: list[str] = Field(default_factory=list)
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


class ArticleGenerationTask(SQLModel, table=True):
    """文章生成任务（持久化任务表 article_generation_task）。

    任务状态、检查点 thread_id、执行节点、审批信息全部入库：
      - 前端轮询 GET /v1/articles/tasks/{task_id} 直接查表，不依赖内存；
      - 进程重启后任务仍在，waiting_approval 的任务凭 thread_id 从
        LangGraph checkpointer 恢复断点（Postgres 模式下跨进程续跑）；
      - 运行上下文（素材）不入库，凭 event_id 重读 article_news 重建。
    """

    __tablename__ = "article_generation_task"
    __table_args__ = (
        UniqueConstraint("task_id", name="ux_article_gen_task_task_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    task_id: str = Field(default="", index=True)
    event_id: int = Field(default=0, index=True)
    event_title: str = Field(default="")
    # queued / running / waiting_approval / done / failed
    status: str = Field(default="queued", index=True)
    error: str = ""
    thread_id: str = ""             # LangGraph checkpointer 的检查点线程 id
    article_id: int = 0
    article_uuid: str = ""
    current_step: str = ""          # 执行到哪一步（工作流节点名，如 generate_draft）
    # 是否人工审核：重启续跑 queued 任务（checkpoint 里还没有这个 state）时需要
    need_review: bool = True
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    # HITL：工作流暂停时的待审信息（前端据此渲染审批卡）
    review_stage: str = ""          # outline / final
    review_title: str = ""
    review_content: str = Field(default="", sa_column=Column(Text))
    review_options: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    # worker 模式专用：API 审批接口把决定写进表里（不做进程内执行），
    # worker 领取后消费（构造 resume Command）并清空，防止重复消费。
    review_decision: str = ""       # pass / modify / reject（空=没有待消费的决定）
    review_suggest: str = Field(default="", sa_column=Column(Text))
    # 领用与心跳：worker CAS 领取时写入；心跳超时的 running 任务可被其他
    # worker（或重启后的自己）接管续跑，checkpoint 保证从断点继续。
    claimed_by: str = ""            # 领用者标识（worker 进程 id）
    heartbeat_at: str = ""          # 最近一次段执行完成时间（ISO 带时区）


class GenerationTask(BaseModel):
    """生成任务的公共视图（API 响应 DTO，由 ArticleGenerationTask 表模型投影）。"""

    task_id: str
    event_id: int
    event_title: str = ""
    # queued / running / waiting_approval / done / failed
    status: str = "queued"
    error: str = ""
    thread_id: str = ""
    article_id: int = 0
    article_uuid: str = ""
    current_step: str = ""          # 执行到哪一步（工作流节点名）
    need_review: bool = True
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    # HITL：工作流暂停时的待审信息（前端据此渲染审批卡）
    review_stage: str = ""          # outline / final
    review_title: str = ""
    review_content: str = ""
    review_options: list[str] = Field(default_factory=list)
    # worker 模式：待消费的审批决定与领用痕迹（内部编排字段，前端可忽略）
    review_decision: str = ""
    review_suggest: str = ""
    claimed_by: str = ""
    heartbeat_at: str = ""

    @classmethod
    def from_row(cls, row: ArticleGenerationTask) -> "GenerationTask":
        """表模型 -> 公共视图（显式投影，避免把主键 id 暴露给前端）。"""
        return cls(
            task_id=row.task_id,
            event_id=row.event_id,
            event_title=row.event_title,
            status=row.status,
            error=row.error,
            thread_id=row.thread_id,
            article_id=row.article_id,
            article_uuid=row.article_uuid,
            current_step=row.current_step,
            need_review=bool(row.need_review),
            created_at=row.created_at,
            started_at=row.started_at,
            finished_at=row.finished_at,
            review_stage=row.review_stage,
            review_title=row.review_title,
            review_content=row.review_content,
            review_options=[str(o) for o in (row.review_options or [])],
            review_decision=str(row.review_decision or ""),
            review_suggest=str(row.review_suggest or ""),
            claimed_by=str(row.claimed_by or ""),
            heartbeat_at=str(row.heartbeat_at or ""),
        )


class CollectStats(BaseModel):
    """一轮采集的统计。"""

    topics: int = 0
    articles: int = 0
    skipped: int = 0
    error: str = ""
