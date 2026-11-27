"""Checkpointer 初始化：LangGraph 断点持久化的后端选择。

优先级（与重构前行为一致）：
    1. PostgresSaver   生产模式：database_dsn（AP_DATABASE_URL / AP_PG_*）
                       配置了 DSN 就用 Postgres 连接池（psycopg_pool），
                       断线自动重连，进程重启后断点不丢；
    2. SqliteSaver     开发/调试模式：显式设置 AP_CHECKPOINT_SQLITE=<文件路径>
                       且未配置 DSN 时启用（langgraph-checkpoint-sqlite）。
                       ⚠️ SQLite 有文件锁，同一个库文件不支持多进程并发写；
    3. MemorySaver     兜底：无 DSN 且未配 SQLite 文件时用进程内内存，
                       重启即失，仅影响断点续跑，不影响正常生成。

扩展位：如需 Celery/多实例部署，把这里替换为 PostgresSaver 即可（已就绪），
业务代码只依赖 get_checkpointer() 的返回接口，不感知具体实现。
"""

from ...core.logger import logger

from ...core.config import get_settings

_CHECKPOINTER = None


def get_checkpointer():
    """惰性构建并缓存 checkpointer（同一进程只初始化一次）。

    Postgres 用 psycopg_pool 连接池而非单连接：Postgres 重启 / 网络抖动把
    旧连接打断时（psycopg 报 OperationalError: server closed the connection
    unexpectedly），池会在下次取连接时自动重建，长跑数分钟的生成段不会
    因一次连接中断而整体失败。
    """
    global _CHECKPOINTER
    if _CHECKPOINTER is not None:
        return _CHECKPOINTER

    settings = get_settings()

    dsn = settings.database_dsn
    if dsn:
        try:
            from psycopg_pool import ConnectionPool
            from langgraph.checkpoint.postgres import PostgresSaver

            # autocommit 是 PostgresSaver 的硬要求；
            # prepare_threshold=None 适配 PgBouncer 事务池（与业务库同源约束）
            pool = ConnectionPool(
                dsn,
                min_size=1,
                max_size=4,
                open=True,
                kwargs={"autocommit": True, "prepare_threshold": None},
            )
            checkpointer = PostgresSaver(pool)
            checkpointer.setup()  # 幂等：创建 checkpoint 表
            _CHECKPOINTER = checkpointer
            logger.info("[saver] 检查点已连接 Postgres 连接池（psycopg_pool，断线自动重连）")
            return _CHECKPOINTER
        except Exception as exc:
            logger.warning(f"[saver] ⚠️ Postgres 检查点不可用，降级："
                           f"{type(exc).__name__}: {exc}")

    sqlite_path = settings.AP_CHECKPOINT_SQLITE.strip()
    if not dsn and sqlite_path:
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver

            conn = _open_sqlite(sqlite_path)
            _CHECKPOINTER = SqliteSaver(conn)
            logger.info(f"[saver] 检查点使用 SQLite 文件（开发模式）：{sqlite_path}")
            return _CHECKPOINTER
        except ImportError:
            logger.warning(
                "[saver] ⚠️ 未安装 langgraph-checkpoint-sqlite，"
                "请执行：uv add langgraph-checkpoint-sqlite（或 pip install）")
        except Exception as exc:
            logger.warning(f"[saver] ⚠️ SQLite 检查点不可用，降级内存："
                           f"{type(exc).__name__}: {exc}")
    elif not dsn:
        logger.warning("[saver] ⚠️ 未配置数据库 DSN，LangGraph 检查点使用进程内内存")

    from langgraph.checkpoint.memory import MemorySaver

    _CHECKPOINTER = MemorySaver()
    return _CHECKPOINTER


def _open_sqlite(path: str):
    """打开 SQLite 连接（SqliteSaver 要求 check_same_thread=False）。"""
    import sqlite3
    from pathlib import Path

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(
        path,
        check_same_thread=False,
    )
