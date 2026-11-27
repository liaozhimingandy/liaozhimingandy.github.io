"""AP（Also Apps）后端：FastAPI。

职责严格限定为三类，绝不接触用户数据明文：
  1. 托管 Vite 构建产物（前端 SPA），并提供 history 路由回退；
  2. 提供元信息接口（health/version/auth-mode）与「工具注册表」API（全局元数据）；
  3. 提供「公共配置表」API（用户密文配置的云端存取）；
  4. 提供 article 流水线 API（自媒体热点采集/聚合/文章生成，见 app/article/router.py，
     后台调度在 lifespan 启停，可用 ARTICLE_SCHEDULER_ENABLED=0 关闭）。
零知识边界：公共配置表存的 value 是不透明密文 blob。后端不定义账户/条目明文模型、
不解密、不解析 value 内容、不记录明文，也不接触用户密钥。所有加解密在浏览器端完成。
schema_version 仅透传 value 内部结构版本、updated_by_device 仅记录设备标识，二者都不涉及明文。
用户身份来自鉴权层注入的 user_sub：logto 模式来自校验过的 JWT（不可伪造）；
passthrough/dev 模式下来自客户端声明的 X-User-Sub（**可伪造**，过渡态，勿用于正式多用户）。
工具注册表 tools 是非敏感全局元数据，不含用户数据、无需 RLS。

生产建议：AP_AUTH_MODE=logto + AP_STORE=postgres 并配置相应环境变量。
默认 passthrough（暂时不鉴权）+ memory，开箱即用、无外部依赖；
passthrough 信任客户端声明的 X-User-Sub，正式多用户上线前必须切 logto（见 /v1/auth/mode）。
"""


from __future__ import annotations
from app.core.logger import logger

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import config, runtime
from app.article.router import router as article_router
from app.article import scheduler as article_scheduler
from app.article.graph.router import router as article_graph_router
from app.portal import router as portal_router
from app.portal import admin_router as portal_admin_router
from app.portal import configs_router as configs_router
from app.portal.models import PortalError
from app.schemas import APP_ERROR_CODES, HealthResponse, ServiceStatus, VersionResponse

API_PREFIX = "/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动装配依赖、自动建表与种子；关停释放引擎。不加载任何用户数据。

    数据层：portal/article 全部走 core.database 的 SQLModel 异步引擎，
    init_db() 用 SQLModel.metadata.create_all 创建不存在的表（幂等，无 DDL 文件）；
    Postgres 不可达时降级 SQLite 内存库（数据不落盘，服务不拒绝启动）。
    """
    runtime.wire(app)
    ready = config.dist_index_exists()
    # article 流水线：SQLModel 自动建表，再启动采集/聚合两个 asyncio 周期任务
    from app.core import database
    from app.portal.service import PortalService
    from app.core.database import session_factory

    if not await database.init_db():
        logger.info("[db] 数据库不可用，已降级 SQLite 内存库（数据不落盘）")
    # 生成任务恢复：重启遗留的 running/queued 自动接续——有 checkpoint 从
    # 报错节点续跑、停在审核点的还原审批卡，不再一律标失败让用户重来。
    from app.article import service as article_service
    await article_service.migrate_task_columns()
    await article_service.recover_stale_tasks()
    # 存量时间列升级为 timestamptz（幂等；SQLite/降级引擎自动跳过）
    await article_service.migrate_time_columns()
    # article 表补 cover_image 列（存量库幂等补列，配图后处理落库用）
    await article_service.migrate_article_columns()
    # 门户种子：幂等（按 code 缺席才插入），空库/内存库生效，已迁移的 PG 表自动跳过
    async with session_factory()() as session:
        await PortalService(session).seed_if_empty()
    store_label = config.store_backend()
    logger.info(
        f"[tools] frontend_ready={ready} dist={config.DIST_DIR} "
        f"store={store_label} auth={app.state.auth_provider.mode}"
    )
    if config.article_scheduler_enabled():
        await article_scheduler.start()
    else:
        logger.info("[article-scheduler] 已通过 ARTICLE_SCHEDULER_ENABLED=0 关闭")
    yield
    await article_scheduler.stop()
    await database.dispose_engine()


app = FastAPI(
    title="AP backend",
    version=config.APP_VERSION,
    description="Static SPA host + zero-knowledge config store + metadata only.",
    lifespan=lifespan,
)

# 跨域：前端部署在 GitHub Pages（https://<user>.github.io），后端在云主机独立域名，
# 属跨源调用，须把 Pages 源加入白名单（AP_CORS_ORIGINS）。默认空 = 仅同源。
# 注意：CORS 是浏览器侧约束，不替代鉴权；passthrough 阶段身份安全由 auth 模式负责。
# allow_credentials=False：本方案用自定义头 X-User-Sub / Authorization 传身份，不依赖 Cookie。
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-User-Sub", "If-Match"],
    expose_headers=["ETag"],
    max_age=600,
)


# --------------------------------------------------------------------------- #
# 统一错误响应：把 HTTPException.detail / 校验错误摊平成规范 ErrorResponse，
# 不含堆栈、内部路径或用户数据。
# --------------------------------------------------------------------------- #


def _error_body(status: int, code: str, message: str, extra: dict | None = None) -> dict:
    body: dict = {"error": code, "message": message}
    if extra:
        body.update(extra)
    return body


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        body = detail  # 路由已构造好规范形状（可能含 detail/conflict 字段）
        return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)
    code = APP_ERROR_CODES.get(exc.status_code, "HTTP_ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.status_code, code, str(detail)),
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=_error_body(422, "VALIDATION_ERROR", "请求参数校验失败"),
    )


@app.exception_handler(PortalError)
async def portal_error_handler(request: Request, exc: PortalError) -> JSONResponse:
    """门户领域异常摊平为统一错误形状，避免泄漏堆栈与内部路径。"""
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.status_code, exc.code, str(exc)),
    )


# --------------------------------------------------------------------------- #
# 元信息接口
# --------------------------------------------------------------------------- #


@app.get(f"{API_PREFIX}/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    """健康检查。frontend_ready=false 表示 dist 尚未构建，但服务本身可用。"""
    return HealthResponse(
        status=ServiceStatus.OK,
        frontend_ready=config.dist_index_exists(),
    )


@app.get(f"{API_PREFIX}/version", response_model=VersionResponse, tags=["meta"])
def version() -> VersionResponse:
    """版本信息：应用版本 + 已安装的工程规范版本（统一版本记录）。"""
    return VersionResponse(
        app_version=config.APP_VERSION,
        standards_version=config.read_standards_version(),
        zero_knowledge=True,
    )


# 公共配置表 API（/v1/auth/mode 与 /v1/configs/*）
app.include_router(configs_router)

# Also Apps 门户 API（公开目录 / 用户功能 / 管理后台）
app.include_router(portal_router)
app.include_router(portal_admin_router)

# 自媒体热点文章流水线（话题选择 -> 生成任务 -> 文章查询）
app.include_router(article_router)

# 工作流调试/编排接口（SSE 流式执行、状态/快照、DAG 图结构，供前端画布）
app.include_router(article_graph_router)


# --------------------------------------------------------------------------- #
# 静态资源与 SPA 回退（放最后，避免吞掉 API 路由）
# --------------------------------------------------------------------------- #

if config.DIST_DIR.is_dir():
    _assets_dir = config.DIST_DIR / "assets"
    # base=/ap/ 时 index.html 以绝对路径请求 /ap/assets/*.js；同份 assets
    # 挂到所有需要的路径（/assets 与 /ap/assets），否则 JS 请求会落进 SPA 回退
    # 拿到 index.html（HTML 当 JS 解析 → 空白页）。工具名/基路径由 AP_PUBLIC_PATH 控制，
    # 与前端 Vite base 保持一致。
    for _i, _mount_path in enumerate(config.assets_mount_paths()):
        app.mount(_mount_path, StaticFiles(directory=_assets_dir, check_dir=False), name=f"assets_{_i}")


# 采集图片静态目录（image_store.IMAGE_DIR）：文章封面/正文配图按
# /images/<热点文件夹>/<uuid7>.jpg 访问；基路径非根时补 /ap/images。
# 注意必须在 SPA 回退路由之前挂载，否则 /images/* 会被兜底成 index.html。
from app.article.image_store import IMAGE_DIR as _IMAGE_DIR  # noqa: E402

_image_mount_paths = ["/images"]
if config.public_prefix() and f"/{config.public_prefix()}/images" not in _image_mount_paths:
    _image_mount_paths.append(f"/{config.public_prefix()}/images")
for _i, _mount_path in enumerate(_image_mount_paths):
    app.mount(_mount_path, StaticFiles(directory=_IMAGE_DIR, check_dir=False), name=f"images_{_i}")


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    """SPA 回退：非 /v1 路径优先直出 dist 内真实文件，否则返回 index.html。

    前端是 hash 路由（/#/safekeep），hash 不发给服务器，故这里主要兜底根路径、
    /ap/ 前缀与 favicon 等静态文件。base 前缀（如 'tools/'）需先剥离，才能把
    /ap/favicon.ico 映射到 dist/favicon.ico；同时保留目录穿越防护。
    """
    if full_path.startswith("v1/") or full_path == "v1":
        return JSONResponse(
            status_code=404,
            content=_error_body(404, "NOT_FOUND", "接口不存在"),
        )

    dist = config.DIST_DIR
    dist_root = dist.resolve()
    # 剥离公网基路径前缀（默认 'ap'），使其后按 dist 内相对路径解析。
    prefix = config.public_prefix()
    rel = full_path
    if prefix:
        if rel == prefix:
            rel = ""
        elif rel.startswith(prefix + "/"):
            rel = rel[len(prefix) + 1 :]

    candidate = (dist / rel).resolve()
    if candidate.is_file() and dist_root in candidate.parents:
        return FileResponse(candidate)

    index = dist / "index.html"
    if index.is_file():
        return FileResponse(index)

    return JSONResponse(
        status_code=503,
        content=_error_body(503, "FRONTEND_NOT_BUILT", "前端尚未构建，请先在 frontend/ 执行 npm run build"),
    )


def main() -> None:
    """本地启动入口：python main.py（或 uvicorn main:app）。仅监听回环地址。"""
    import uvicorn

    uvicorn.run(
        "main:app",
        host=config.bind_host(),
        port=config.bind_port(),
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
