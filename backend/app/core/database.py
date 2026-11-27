"""article 流水线数据基础设施：SQLModel 异步引擎与会话工厂。

分层位置（与参考项目 tuiwen 的 core/database.py 同构）：
    API / scheduler / collector / cluster
      ↓ 传入 AsyncSession
    service（事务边界，commit/rollback 出口）
      ↓
    dal（BaseDAO + 各表 DAO，只 flush 不 commit）
      ↓
    SQLModel / SQLAlchemy AsyncEngine
      ↓
    PostgreSQL（postgresql+psycopg 驱动，复用现有 AP_DATABASE_URL / AP_PG_* 配置）
    或 SQLite 内存库（AP_STORE=memory / 测试，aiosqlite 驱动）

建表：FastAPI 官方/SQLModel 惯例 —— 表模型集中在 app.article.models，
init_db() 通过 SQLModel.metadata.create_all 创建「不存在的表」，不写任何 DDL 文件。
NOTE: create_all 不会给已有表加列；改表结构仍需手工迁移。

事务原则：
    DAO 只 flush 不 commit；事务出口统一在 service 层
    （请求内用 get_session 依赖 + service 显式 commit，
    后台任务用 session_scope 上下文自动提交/回滚）。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from .logger import logger

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from .config import get_settings


def _log(message: str) -> None:
    logger.info(f"[article-db] {message}")


# --------------------------------------------------------------------------- #
# 引擎：按 AP_STORE / DSN 选择 Postgres / SQLite 内存库（惰性构建，单例）
# --------------------------------------------------------------------------- #

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _database_url() -> str:
    """组装 SQLAlchemy 异步连接串。

    Postgres 走 psycopg3 异步方言（postgresql+psycopg://），DSN 来自 Settings
    （AP_DATABASE_URL 或 AP_PG_* 分散变量）；memory/测试走 sqlite+aiosqlite
    内存库（配合 StaticPool 共享同一连接，否则 :memory: 每个连接各自一张空库）。
    """
    settings = get_settings()
    if settings.AP_STORE.strip().lower() == "postgres" or settings.dsn_configured():
        dsn = settings.database_dsn
        if dsn:
            if dsn.startswith("postgresql+"):
                return dsn
            for prefix in ("postgresql://", "postgres://"):
                if dsn.startswith(prefix):
                    return dsn.replace(prefix, "postgresql+psycopg://", 1)
        _log("AP_STORE=postgres 但 DSN 未配置完整，降级使用 SQLite 内存库")
    return "sqlite+aiosqlite://"  # 内存库


def _build_engine() -> AsyncEngine:
    from sqlalchemy.ext.asyncio import create_async_engine

    url = _database_url()
    if url.startswith("sqlite"):
        engine = create_async_engine(
            url,
            echo=False,
            poolclass=StaticPool,          # 单连接共享，内存库表对全部会话可见
            connect_args={"check_same_thread": False},
        )
        _log("SQLite 内存库引擎就绪（数据不落盘，重启即失）")
        return engine

    engine = create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,                # 失效连接自动检测重连
        pool_recycle=3600,
        pool_size=get_settings().pg_pool_max_size(4),
        # PgBouncer 事务池模式下不能使用服务端预编译语句（prepare_threshold=None，
        # 与 psycopg 侧的适配同源）
        connect_args=get_settings().pg_connect_kwargs,
    )
    _log("PostgreSQL 异步引擎就绪（postgresql+psycopg）")
    return engine


def get_engine() -> AsyncEngine:
    """取当前引擎（惰性创建）。测试可用 reset_engine() 注入独立引擎。"""
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def session_factory() -> async_sessionmaker[AsyncSession]:
    """取当前会话工厂（绑定当前引擎）。

    expire_on_commit=False：commit 后 ORM 实例属性仍可读（DAO/服务层约定依赖此行为）；
    autoflush=False：避免查询前隐式 flush 带来的意外写库。
    """
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


def reset_engine(engine: AsyncEngine | None = None) -> None:
    """替换当前引擎与会话工厂（测试隔离用）。

    engine=None 表示清空，下次 get_engine() 按配置重建。
    注意：不负责关闭旧引擎，调用方自行 dispose。
    """
    global _engine, _session_factory
    _engine = engine
    _session_factory = None


def use_memory_engine() -> AsyncEngine:
    """强制切换到全新的 SQLite 内存引擎（测试隔离 / 降级用）。

    每次调用都是一块空白库；调用方自行管理建表（init_tables）与释放。
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    reset_engine(engine)
    return engine


async def get_session():
    """FastAPI 依赖：请求级会话，请求结束自动关闭；不自动 commit（出口在 service）。"""
    async with session_factory()() as session:
        yield session


@asynccontextmanager
async def session_scope():
    """后台任务用的事务边界：正常退出 commit，异常回滚并上抛。"""
    async with session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# --------------------------------------------------------------------------- #
# 建表：SQLModel 自动建表（FastAPI 官方惯例，不写 DDL 文件）
# --------------------------------------------------------------------------- #

def _import_all_models() -> None:
    """集中导入全部表模型，确保注册进 SQLModel.metadata。

    新增表模型后记得在这里补一行导入，否则 create_all 不会建那张表。
    """
    from ..article import models  # noqa: F401
    from ..portal import models as _portal_models  # noqa: F401


async def init_tables(engine: AsyncEngine | None = None) -> None:
    """在指定引擎（默认当前引擎）上创建全部不存在的表。测试直接建内存表用。"""
    _import_all_models()
    target = engine if engine is not None else get_engine()
    async with target.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def init_db() -> bool:
    """初始化数据库：仅创建不存在的表（不删数据、不改已有表结构）。

    Postgres 不可达时降级为 SQLite 内存引擎并重建表（服务不因库故障拒绝启动，
    行为与原 DAL 的降级策略一致）。返回 False 表示已降级（数据不落盘）。
    """
    try:
        await init_tables()
        return True
    except Exception as exc:
        _log(f"数据库初始化失败，降级 SQLite 内存库：{type(exc).__name__}: {exc}")
        use_memory_engine()
        await init_tables()
        return False


async def dispose_engine() -> None:
    """释放当前引擎的所有连接（应用停机时调用）。"""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        _log("数据库引擎已释放")
