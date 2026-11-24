"""工具准入注册表（以 portal_apps 为唯一数据源）。

分工（本轮起 tools 表已下线，见 sql/007_drop_tools_and_seed_safekeep.sql）：
  - portal_apps：应用目录唯一权威。configs 接口的 tool_id 准入语义 =
    「portal_apps 中存在该 code 且 status=published 的应用」。
  - tool_configs（store.py）：某用户某工具下的密文配置，RLS 行级隔离。

实现：
  - ToolRepository 协议：get / list / exists_enabled（保持 /v1/tools 形状不变）。
  - PortalToolRegistry：生产实现，包装 PortalRepository，按 code 映射应用。
    enabled ≙ status='published'；tool_id ≙ code 小写（configs 路由用小写）。
    配额覆盖恒为 None（沿用全局 config 默认值）。
  - MemoryToolRepository：测试/内存兜底用的独立种子实现（不依赖任何表）。

配额语义：本模块不再提供每工具配额覆盖；MemoryToolRepository 保留字段仅为
兼容既有单测对配额解析逻辑的覆盖。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolRecord:
    """一条工具元信息（portal 应用的投影）。不含任何用户数据。"""

    tool_id: str
    name: str
    icon: str
    description: str
    enabled: bool
    sort_order: int
    default_max_keys: int | None
    default_max_value_bytes: int | None
    created_at: str
    updated_at: str

    def to_public(self) -> dict[str, Any]:
        """对外形状：工具元信息，可安全下发给已认证前端。"""
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "icon": self.icon,
            "description": self.description,
            "enabled": self.enabled,
            "sort_order": self.sort_order,
            "default_max_keys": self.default_max_keys,
            "default_max_value_bytes": self.default_max_value_bytes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ToolRepository(Protocol):
    """只读工具准入契约。所有方法都不涉及用户身份。"""

    def get(self, tool_id: str) -> ToolRecord | None:
        """按 id 取工具（含已禁用，便于管理端区分 404 与 410）。"""
        ...

    def list(self, *, enabled_only: bool = True) -> list[ToolRecord]:
        """列出工具，默认只返回启用项，按 sort_order 排序。"""
        ...

    def exists_enabled(self, tool_id: str) -> bool:
        """工具存在且启用——写配置的准入判定。"""
        ...


class PortalToolRegistry:
    """生产实现：以 portal_apps 为权威数据源，包装 PortalRepository。

    - exists_enabled(tool_id)：存在 code 匹配（大小写不敏感）且 status='published' 的应用。
    - tool_id 对外统一小写（configs 路由与前端均用小写），portal code 为大写。
    - 不持有连接：直接复用门户仓储的连接池，避免多一份池带来的连接浪费。
    """

    def __init__(self, portal: Any) -> None:
        # portal: PortalRepository（避免循环 import，运行期鸭子类型）
        self._portal = portal

    @staticmethod
    def _to_record(app: Any) -> ToolRecord:
        enabled = app.status == "published"
        return ToolRecord(
            tool_id=app.code.lower(),
            name=app.name,
            icon=app.icon_url or "",
            description=app.subtitle or app.description or "",
            enabled=enabled,
            sort_order=app.sort_order,
            default_max_keys=None,
            default_max_value_bytes=None,
            created_at=app.created_at,
            updated_at=app.updated_at,
        )

    def get(self, tool_id: str) -> ToolRecord | None:
        app = self._portal.get_app_by_code(tool_id)
        return self._to_record(app) if app is not None else None

    def list(self, *, enabled_only: bool = True) -> list[ToolRecord]:
        apps = self._portal.list_apps(status="published" if enabled_only else None)
        rows = [self._to_record(a) for a in apps]
        return sorted(rows, key=lambda t: (t.sort_order, t.tool_id))

    def exists_enabled(self, tool_id: str) -> bool:
        app = self._portal.get_app_by_code(tool_id)
        return app is not None and app.status == "published"


# 内存种子：锦囊。仅用于 memory 存储模式与单测，生产以 portal_apps 为准。
# 定义必须晚于 ToolRecord（否则 NameError）。
DEFAULT_TOOLS: tuple[ToolRecord, ...] = (
    ToolRecord(
        tool_id="safekeep",
        name="锦囊",
        icon="lock-on",
        description="零知识在线密码保险库",
        enabled=True,
        sort_order=10,
        default_max_keys=None,
        default_max_value_bytes=None,
        created_at="seed",
        updated_at="seed",
    ),
)


class MemoryToolRepository:
    """进程内实现：测试/内存兜底用。可用 seed() 注入自定义工具。"""

    def __init__(self, tools: tuple[ToolRecord, ...] | list[ToolRecord] = DEFAULT_TOOLS) -> None:
        self._data: dict[str, ToolRecord] = {t.tool_id: t for t in tools}

    def seed(self, *tools: ToolRecord) -> None:
        """测试/启动期注入或覆盖工具记录。"""
        for t in tools:
            self._data[t.tool_id] = t

    def get(self, tool_id: str) -> ToolRecord | None:
        return self._data.get(tool_id)

    def list(self, *, enabled_only: bool = True) -> list[ToolRecord]:
        rows = [t for t in self._data.values() if (t.enabled or not enabled_only)]
        return sorted(rows, key=lambda t: (t.sort_order, t.tool_id))

    def exists_enabled(self, tool_id: str) -> bool:
        t = self._data.get(tool_id)
        return bool(t and t.enabled)
