"""兼容 shim：旧函数式配置入口委托给 core.config.Settings 单例。

新代码请直接用 Settings：
    from .core.config import get_settings
    settings = get_settings()

本文件保留旧函数签名（app 内仍有调用点、测试有 mock.patch 目标），
每个函数现场读取单例属性。全部函数已迁移后本文件可删除。
"""

from __future__ import annotations

from pathlib import Path

from .core.config import (  # noqa: F401  再导出
    APP_VERSION,
    BACKEND_DIR,
    DIST_DIR,
    PROJECT_ROOT,
    STANDARDS_VERSION_FILE,
    Settings,
    get_settings,
    read_standards_version,
    reload_settings,
)

def dist_index_exists() -> bool:
    return get_settings() is not None and (DIST_DIR / "index.html").is_file()


def bind_host() -> str:
    """监听地址。本地默认仅 127.0.0.1；容器部署须显式设 AP_HOST=0.0.0.0。"""
    return get_settings().AP_HOST.strip() or "127.0.0.1"


def bind_port() -> int:
    try:
        return int(get_settings().AP_PORT)
    except (TypeError, ValueError):
        return 8080


# --------------------------------------------------------------------------- #
# 前端公网基路径
# --------------------------------------------------------------------------- #

def public_path() -> str:
    return get_settings().public_path


def public_prefix() -> str:
    return get_settings().public_prefix


def assets_mount_paths() -> list[str]:
    return get_settings().assets_mount_paths


# --------------------------------------------------------------------------- #
# 存储后端与 Postgres 连接
# --------------------------------------------------------------------------- #

def store_backend() -> str:
    """存储后端：memory（默认）| postgres。"""
    return get_settings().AP_STORE.strip().lower()


def database_url() -> str:
    """PostgreSQL DSN（psycopg 可直接使用的 postgresql:// URL 或 libpq conninfo）。"""
    return get_settings().database_dsn


def pg_connect_kwargs() -> dict:
    return get_settings().pg_connect_kwargs


def pg_pool_max_size(default: int = 8) -> int:
    return get_settings().pg_pool_max_size(default)


def pg_pool_timeout(default: int = 10) -> float:
    return get_settings().pg_pool_timeout(float(default))


def pg_pool_max_lifetime(default: int = 300) -> int:
    return get_settings().pg_pool_max_lifetime(default)


def cors_origins() -> list[str]:
    return get_settings().cors_origin_list


# --------------------------------------------------------------------------- #
# 鉴权配置
# --------------------------------------------------------------------------- #

def auth_mode() -> str:
    """鉴权模式：passthrough（默认，暂时不鉴权）| dev | logto | stub。"""
    return get_settings().AP_AUTH_MODE.strip().lower()


def dev_auth_header() -> str:
    return get_settings().AP_DEV_AUTH_HEADER.strip() or "X-User-Sub"


def passthrough_default_sub() -> str:
    return get_settings().AP_PASSTHROUGH_DEFAULT_SUB.strip() or "anonymous"


def logto_issuer() -> str:
    return get_settings().LOGTO_ISSUER.strip()


def logto_audience() -> str:
    return get_settings().LOGTO_AUDIENCE.strip()


def logto_jwks_url() -> str:
    return get_settings().LOGTO_JWKS_URL.strip()


# --------------------------------------------------------------------------- #
# 配额与白名单
# --------------------------------------------------------------------------- #

def max_value_bytes() -> int:
    return max(1, int(get_settings().AP_MAX_VALUE_BYTES))


def max_keys_per_user_tool() -> int:
    return max(1, int(get_settings().AP_MAX_KEYS))


def allowed_tool_ids() -> set[str]:
    return get_settings().allowed_tool_id_set


def portal_admin_subs() -> set[str]:
    return get_settings().portal_admin_sub_set


# --------------------------------------------------------------------------- #
# article 流水线配置
# --------------------------------------------------------------------------- #

def article_scheduler_enabled() -> bool:
    return bool(get_settings().ARTICLE_SCHEDULER_ENABLED)


def article_collect_interval_minutes() -> int:
    return max(0, int(get_settings().ARTICLE_COLLECT_INTERVAL_MINUTES))


def article_cluster_interval_minutes() -> int:
    return max(0, int(get_settings().ARTICLE_CLUSTER_INTERVAL_MINUTES))


def article_scheduler_start_delay_sec() -> int:
    return max(0, int(get_settings().ARTICLE_SCHEDULER_START_DELAY_SEC))


def article_generate_require_admin() -> bool:
    return bool(get_settings().ARTICLE_GENERATE_REQUIRE_ADMIN)
