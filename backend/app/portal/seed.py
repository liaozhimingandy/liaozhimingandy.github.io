"""门户默认种子（与 sql/005_apps_portal_seed.sql 内容对应）。

两处种子必须保持一致：PG 走 SQL 迁移，SQLite 内存库/空库走这里
（service.seed_if_empty 幂等插入：code 已存在即跳过）。
已确认可访问的只有 Also Account；其余保持 draft + 空 launch_url，不编造地址。
"""

from __future__ import annotations

from datetime import datetime, timezone

from .models import AppCategory, PortalApp


def _category(code: str, name: str, description: str, icon: str,
              sort_order: int) -> AppCategory:
    return AppCategory(
        code=code, name=name, description=description, icon=icon,
        sort_order=sort_order, status="enabled",
    )


DEFAULT_CATEGORIES: tuple[AppCategory, ...] = (
    _category("all", "全部应用", "浏览所有应用", "apps", 0),
    _category("ai", "AI 工具", "人工智能相关应用与工具", "ai", 10),
    _category("productivity", "效率工具", "提升工作与协作效率", "desktop", 20),
    _category("creation", "内容创作", "写作、设计、音视频创作", "palette", 30),
    _category("game", "游戏娱乐", "休闲游戏与娱乐应用", "gamepad", 40),
    _category("finance", "金融投资", "量化、行情与投资研究", "chart-bar", 50),
    _category("social", "社交社区", "沟通与社区类应用", "usergroup", 60),
    _category("other", "其他服务", "未归类的服务与应用", "server", 70),
)


def _app(
    code: str,
    name: str,
    subtitle: str,
    description: str,
    *,
    app_type: str = "application",
    icon_url: str = "",
    launch_url: str = "",
    status: str = "draft",
    published: bool = False,
    auth_required: bool = False,
    featured: bool = False,
    home: bool = False,
    is_new: bool = False,
    sort_order: int = 0,
) -> PortalApp:
    return PortalApp(
        code=code,
        name=name,
        subtitle=subtitle,
        description=description,
        detail=description,
        icon_url=icon_url,
        launch_url=launch_url,
        app_type=app_type,
        status=status,
        visibility="public",
        auth_required=auth_required,
        is_featured=featured,
        show_on_home=home,
        is_new=is_new,
        sort_order=sort_order,
        published_at=(
            datetime(2026, 1, 1, tzinfo=timezone.utc) if published else None
        ),
    )


# (应用, 分类 code 列表)
DEFAULT_APPS: tuple[tuple[PortalApp, tuple[str, ...]], ...] = (
    (
        _app(
            "SAFEKEEP", "锦囊 SafeKeep", "零知识在线密码保险库",
            "浏览器端 AES-256-GCM 加密，主密码与恢复码双钥匙解锁，服务端只保存密文。",
            app_type="tool", icon_url="/static/icons/safekeep.svg",
            launch_url="/safekeep/", status="published",
            published=True, featured=True, sort_order=5,
        ),
        ("productivity", "other"),
    ),
    (
        _app(
            "ALSO_ACCOUNT", "Also Account", "统一身份认证中心",
            "管理你的 Also 账号、应用授权与登录安全。",
            app_type="service", launch_url="https://account.alsoapp.com/",
            status="published", published=True, featured=True, home=True,
            sort_order=10,
        ),
        ("productivity", "other"),
    ),
    (
        _app(
            "ALSO_TOOLS", "Also Tools", "实用小工具集合",
            "浏览器内运行的零知识小工具，数据留在你的设备。",
            sort_order=20,
        ),
        ("productivity", "other"),
    ),
    (
        _app(
            "THIS_CITY", "thisCity", "城市探索游戏",
            "在真实城市地图中探索、打卡与解锁故事。",
            app_type="game", sort_order=30,
        ),
        ("game", "other"),
    ),
    (
        _app(
            "AI_NEWS", "AI News", "人工智能资讯聚合",
            "每日精选 AI 行业动态、论文与产品发布。",
            sort_order=40,
        ),
        ("ai", "other"),
    ),
    (
        _app(
            "AI_DRAMA", "AI Drama", "AI 短剧创作工作台",
            "分阶段创作、结构化输出，让灵感变成剧本。",
            auth_required=True, is_new=True, sort_order=50,
        ),
        ("ai", "other"),
    ),
    (
        _app(
            "ALPHA_QUANT", "AlphaQuant", "量化交易研究系统",
            "多维因子采集、因子挖掘与策略回测。",
            auth_required=True, sort_order=60,
        ),
        ("ai", "finance", "other"),
    ),
    (
        _app(
            "TUIWEN", "Tuiwen", "推文社区",
            "分享想法、关注感兴趣的人与话题。",
            sort_order=70,
        ),
        ("social", "other"),
    ),
)
