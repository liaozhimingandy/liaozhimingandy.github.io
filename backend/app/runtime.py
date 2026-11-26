"""运行期装配：把鉴权 provider 注入 app.state。

数据层不再走仓储注入：portal/article 全部经 Depends(get_session) ->
Service -> DAO（core.database 统一异步引擎），app.state 只保留鉴权 provider。

好处：
  - main.py 不 import psycopg/PyJWT 的具体类，可选依赖缺席时应用照常启动；
  - 测试可直接替换 app.state.auth_provider，无需 mock 全局；
  - 切换 dev→logto、内存库→postgres 只改环境变量，零代码改动。
"""

from __future__ import annotations

from . import config
from .auth import AuthProvider, LogtoJWTProvider
from .auth import build_provider as _build_provider


def build_auth_provider() -> AuthProvider:
    if config.auth_mode() == "logto":
        return LogtoJWTProvider(
            issuer=config.logto_issuer(),
            audience=config.logto_audience(),
            jwks_url=config.logto_jwks_url(),
        )
    return _build_provider(
        mode=config.auth_mode(),
        dev_header=config.dev_auth_header(),
        passthrough_header=config.dev_auth_header(),
        passthrough_default_sub=config.passthrough_default_sub(),
    )


def logto_configured(provider: AuthProvider) -> bool:
    return isinstance(provider, LogtoJWTProvider) and provider.configured


def wire(app) -> None:
    """把鉴权依赖挂到 app.state，供 API 路由通过 request.app.state 取用。"""
    provider = build_auth_provider()
    app.state.auth_provider = provider
    app.state.logto_configured = logto_configured(provider)


def teardown(app) -> None:
    """关停钩子：鉴权 provider 无需释放，保留以兼容既有调用。"""
    return None
