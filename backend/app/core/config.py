"""全局配置（Settings 单例）：pydantic-settings，.env 自动加载。

参考 tuiwen/core/config.py 的模式：
  - 所有部署期可变项都是 Settings 字段，字段名即环境变量名（大小写不敏感）；
  - 本地开发自动加载 backend/.env；容器/测试环境用系统环境变量
    （真实环境变量优先级高于 .env 文件值）；
  - 对外入口 get_settings()（lru_cache 单例）；需要按新环境重建时用 reload_settings()。

子模块统一从这里读参数：from ..core.config import get_settings
app/config.py 是兼容 shim（路径常量 + 旧函数委托），逐步迁移后可删除。

安全默认：鉴权 passthrough（暂时不鉴权）+ 存储 SQLite 内存库，开箱即用、无外部依赖；
生产：AP_AUTH_MODE=logto + AP_STORE=postgres + 填 DSN 与 Logto 三件套。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 目录结构：
#   backend/app/core/config.py   本文件
#   backend/                     BACKEND_DIR（.env 所在目录）
#   <repo>/                      PROJECT_ROOT
#   frontend/dist/               Vite 构建产物（由 FastAPI 托管）
BACKEND_DIR: Path = Path(__file__).resolve().parent.parent.parent
PROJECT_ROOT: Path = BACKEND_DIR.parent
DIST_DIR: Path = PROJECT_ROOT / "frontend" / "dist"
STANDARDS_VERSION_FILE: Path = PROJECT_ROOT / ".ai-standards" / "VERSION"

APP_VERSION = "0.4.0"
# 规范源未提供时的兜底；真实值由 .ai-standards/VERSION 覆盖
FALLBACK_STANDARDS_VERSION = "unknown"


def parse_csv(v: str | list[str] | None) -> list[str]:
    """逗号分隔字符串 -> 去空白去空项列表；传列表则原样返回。"""
    if v is None:
        return []
    if isinstance(v, list):
        return [str(item).strip() for item in v if str(item).strip()]
    return [item.strip() for item in v.split(",") if item.strip()]


class Settings(BaseSettings):
    """应用全局配置（字段名即环境变量名，大小写不敏感）。"""

    model_config = SettingsConfigDict(
        # 本地开发自动加载 backend/.env；测试用 Settings(_env_file=None) 隔离
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------------------------------------------------------------ 服务基础
    AP_HOST: str = Field("127.0.0.1", description="监听地址；容器须显式 0.0.0.0")
    AP_PORT: int = Field(8080, description="监听端口")
    AP_PUBLIC_PATH: str = Field(
        "/ap/", description="前端公网基路径，须与 Vite base / VITE_PUBLIC_PATH 一致")

    APP_VERSION: str = Field(APP_VERSION, description="应用版本号")

    # ------------------------------------------------------------------ 存储后端
    AP_STORE: str = Field("memory", description="存储后端：memory | postgres")
    AP_DATABASE_URL: str = Field(
        "", description="显式完整 DSN；密码含特殊字符请自行 URL-encode")
    AP_PG_HOST: str = Field("", description="分散变量组装 DSN 用")
    AP_PG_PORT: str = Field("5432", description="Postgres 端口")
    AP_PG_NAME: str = Field("", description="数据库名")
    AP_PG_USER: str = Field("", description="用户名")
    AP_PG_PASSWORD: str = Field("", description="密码")
    AP_PG_SSLMODE: str = Field("", description="sslmode 参数（可选）")
    AP_PG_PREPARE_THRESHOLD: str = Field(
        "off", description="PgBouncer 事务池下必须 off；设整数可重开自动 prepare")
    AP_PG_CONNECT_TIMEOUT: int = Field(10, description="连接超时秒数")
    AP_PG_POOL_MAX: int = Field(8, description="连接池上限（PgBouncer 后端可给小值）")
    AP_PG_POOL_TIMEOUT: float = Field(10.0, description="从池取连接超时秒数")
    AP_PG_POOL_MAX_LIFETIME: int = Field(300, description="连接最大存活秒数")

    # ------------------------------------------------------------------ 鉴权
    AP_AUTH_MODE: str = Field(
        "passthrough", description="鉴权模式：passthrough | dev | logto | stub")
    AP_DEV_AUTH_HEADER: str = Field("X-User-Sub", description="dev 模式身份头")
    AP_PASSTHROUGH_DEFAULT_SUB: str = Field(
        "anonymous", description="passthrough 模式下未带头时的归属槽位")
    LOGTO_ISSUER: str = Field("", description="Logto issuer")
    LOGTO_AUDIENCE: str = Field("", description="Logto audience")
    LOGTO_JWKS_URL: str = Field("", description="Logto JWKS 地址")

    # ------------------------------------------------------------------ 配额与白名单
    AP_MAX_VALUE_BYTES: int = Field(524288, description="单条配置 value 字节上限")
    AP_MAX_KEYS: int = Field(200, description="单用户单工具 key 数上限")
    AP_TOOL_IDS: str = Field("", description="工具 id 白名单（逗号分隔；空=不限制）")
    PORTAL_ADMIN_SUBS: str = Field(
        "", description="门户管理员 Logto sub 白名单（逗号分隔；空=fail-closed）")
    AP_CORS_ORIGINS: str = Field(
        "", description="允许的跨域来源（逗号分隔；空=仅同源）")

    # ------------------------------------------------------------------ article 流水线
    ARTICLE_SCHEDULER_ENABLED: bool = Field(True, description="随服务启动采集/聚合调度")
    ARTICLE_COLLECT_INTERVAL_MINUTES: int = Field(30, description="采集间隔；0=关闭定时")
    ARTICLE_CLUSTER_INTERVAL_MINUTES: int = Field(3, description="聚合间隔；0=关闭定时")
    ARTICLE_SCHEDULER_START_DELAY_SEC: int = Field(60, description="启动后首轮延迟秒数")
    ARTICLE_GENERATE_REQUIRE_ADMIN: bool = Field(
        False, description="触发生成是否要求管理员")
    ARTICLE_HITL_ENABLED: bool = Field(
        True, description="文章生成是否需要人工审核（大纲/终审）；False 时自动通过")

    # ------------------------------------------------------------------ LLM（文章生成）
    LLM_BASE_URL: str = Field("https://llm.alsoapp.com/v1", description="OpenAI 兼容端点")
    LLM_API_KEY: str = Field("", description="LLM API Key")
    LLM_MODEL: str = Field("aim-1", description="生成模型名")
    LLM_RETRIES: int = Field(2, description="LLM 调用失败重试次数")

    # ===================== 计算属性（派生值，环境变量不可覆盖） =====================

    def dsn_configured(self) -> bool:
        """是否具备 Postgres 连接条件（显式 DSN 或 host/user/dbname 三件齐全）。"""
        return bool(self.AP_DATABASE_URL) or bool(
            self.AP_PG_HOST and self.AP_PG_USER and self.AP_PG_NAME)

    @property
    def database_dsn(self) -> str:
        """组装 psycopg 可用的 Postgres DSN；关键项缺失时返回空串（fail-closed 由调用方做）。

        优先级：AP_DATABASE_URL 显式 DSN > 分散变量组装。
        user/password/dbname 做百分号编码——密码含 '@' 等特殊字符时
        不编码会被误当作 host 分隔符导致连库失败。
        """
        explicit = self.AP_DATABASE_URL.strip()
        if explicit:
            return explicit
        host = self.AP_PG_HOST.strip()
        user = self.AP_PG_USER.strip()
        dbname = self.AP_PG_NAME.strip()
        if not (host and user and dbname):
            return ""
        port = self.AP_PG_PORT.strip() or "5432"
        password = self.AP_PG_PASSWORD
        creds = f"{quote(user, safe='')}:{quote(password, safe='')}@" if password \
            else f"{quote(user, safe='')}@"
        url = f"postgresql://{creds}{host}:{port}/{quote(dbname, safe='')}"
        sslmode = self.AP_PG_SSLMODE.strip()
        if sslmode:
            url += f"?sslmode={quote(sslmode, safe='')}"
        return url

    @property
    def public_path(self) -> str:
        """规范化前端基路径：首尾都带斜杠（'/ap/' 或 '/'）。"""
        raw = self.AP_PUBLIC_PATH.strip()
        if not raw or raw == "/":
            return "/"
        if not raw.startswith("/"):
            raw = "/" + raw
        if not raw.endswith("/"):
            raw += "/"
        return raw

    @property
    def public_prefix(self) -> str:
        """去掉首尾斜杠的基路径段（如 'ap'）；根部署返回 ''。"""
        return self.public_path.strip("/")

    @property
    def assets_mount_paths(self) -> list[str]:
        """dist/assets 需挂载的全部 URL 前缀（去重、保序）。

        始终含 '/assets'（兼容 base='/'）；base 非根时再补 '/ap/assets'。
        """
        paths = ["/assets"]
        base = self.public_path
        if base != "/":
            candidate = base.rstrip("/") + "/assets"
            if candidate not in paths:
                paths.append(candidate)
        return paths

    @property
    def cors_origin_list(self) -> list[str]:
        """允许的跨域来源列表（去尾部斜杠）。"""
        return [item.rstrip("/") for item in parse_csv(self.AP_CORS_ORIGINS)]

    @property
    def allowed_tool_id_set(self) -> set[str]:
        """允许的工具 id 白名单；空集合表示不限制（用正则校验形状即可）。"""
        return set(parse_csv(self.AP_TOOL_IDS))

    @property
    def portal_admin_sub_set(self) -> set[str]:
        """门户管理员 sub 白名单；空集合 = 未配置管理员（管理接口 fail-closed）。"""
        return set(parse_csv(self.PORTAL_ADMIN_SUBS))

    @property
    def pg_connect_kwargs(self) -> dict:
        """psycopg connect() 额外参数，适配 PgBouncer 事务池。

        prepare_threshold=None 彻底关闭自动 prepare——事务池模式下服务端
        prepared statement 绑定物理连接，客户端连接复用不同物理连接会
        间歇性报 `prepared statement "_pg3_x" does not exist`。
        """
        raw = self.AP_PG_PREPARE_THRESHOLD.strip().lower()
        threshold: int | None = None
        if raw not in ("", "off", "none", "false", "0"):
            try:
                threshold = max(1, int(raw))
            except ValueError:
                threshold = None
        return {
            "prepare_threshold": threshold,
            "connect_timeout": max(1, int(self.AP_PG_CONNECT_TIMEOUT)),
        }

    def pg_pool_max_size(self, default: int = 8) -> int:
        return max(1, int(self.AP_PG_POOL_MAX)) if self.AP_PG_POOL_MAX > 0 else default

    def pg_pool_timeout(self, default: float = 10.0) -> float:
        return max(1.0, float(self.AP_PG_POOL_TIMEOUT))

    def pg_pool_max_lifetime(self, default: int = 300) -> int:
        return max(30, int(self.AP_PG_POOL_MAX_LIFETIME))

    @model_validator(mode="after")
    def _normalize(self) -> "Settings":
        if not self.APP_VERSION:
            self.APP_VERSION = APP_VERSION
        return self


@lru_cache
def get_settings() -> Settings:
    """全局唯一 Settings 实例（lru_cache 缓存，进程内只构造一次）。"""
    return Settings()


def reload_settings() -> Settings:
    """清缓存重建 Settings（测试/运行期改环境变量后调用）。"""
    get_settings.cache_clear()
    return get_settings()


# --------------------------------------------------------------------------- #
# 纯函数工具（无环境依赖，供 main.py / 测试复用）
# --------------------------------------------------------------------------- #

def read_standards_version() -> str:
    """读取已安装适配配置里的规范版本；文件缺失时回退 unknown。"""
    try:
        value = STANDARDS_VERSION_FILE.read_text(encoding="utf-8").strip()
        return value or FALLBACK_STANDARDS_VERSION
    except (OSError, UnicodeDecodeError):
        return FALLBACK_STANDARDS_VERSION


def dist_index_exists() -> bool:
    """前端构建产物是否就绪。"""
    return (DIST_DIR / "index.html").is_file()
