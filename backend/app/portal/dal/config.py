"""公共配置表 DAO（tool_configs）：零知识密文存取 + 乐观锁 CAS。

语义与旧 store.PostgresRepository / MemoryRepository 一致：
  - put：expected_revision in (None, 0) 仅当不存在时创建（防误覆盖）；
    expected_revision > 0 按行级 CAS 更新（UPDATE ... WHERE revision = %s）；
  - delete：软删除（打墓碑 + revision +1），同样走 CAS；
  - value 是不透明 JSON blob：本层不做任何结构解析。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import update
from sqlmodel import select
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.dal_base import BaseDAO
from ..models import ConflictError, NotFoundError, ToolConfig, utcnow


class ToolConfigDAO(BaseDAO[ToolConfig]):
    model = ToolConfig

    # ------------------------------------------------------------------ 读
    async def get(self, user_sub: str, tool_id: str, key: str) -> ToolConfig | None:
        """取单条（不含软删除）；不存在返回 None。"""
        result = await self._execute(
            select(ToolConfig)
            .where(ToolConfig.user_sub == user_sub, ToolConfig.tool_id == tool_id,
                   ToolConfig.key == key, ToolConfig.deleted_at.is_(None))
            .limit(1),
            "get")
        return result.first()

    async def get_any(self, user_sub: str, tool_id: str, key: str) -> ToolConfig | None:
        """取单条（含软删除行），用于区分「冲突」与「已存在」的当前 revision。"""
        result = await self._execute(
            select(ToolConfig)
            .where(ToolConfig.user_sub == user_sub, ToolConfig.tool_id == tool_id,
                   ToolConfig.key == key)
            .limit(1),
            "get_any")
        return result.first()

    async def list(self, user_sub: str, tool_id: str,
                   *, include_deleted: bool = False) -> list[ToolConfig]:
        stmt = select(ToolConfig).where(
            ToolConfig.user_sub == user_sub, ToolConfig.tool_id == tool_id)
        if not include_deleted:
            stmt = stmt.where(ToolConfig.deleted_at.is_(None))
        stmt = stmt.order_by(ToolConfig.key)
        return list((await self._execute(stmt, "list")).all())

    async def count_keys(self, user_sub: str, tool_id: str) -> int:
        """活跃（未删除）key 数量，配额判定用。"""
        rows = await self.list(user_sub, tool_id)
        return len(rows)

    # ------------------------------------------------------------------ 写（CAS）
    async def put(
        self,
        user_sub: str,
        tool_id: str,
        key: str,
        value: Any,
        *,
        expected_revision: int | None,
        schema_version: int = 1,
        updated_by_device: str | None = None,
    ) -> ToolConfig:
        """UPSERT + CAS。冲突/重复创建抛 ConflictError(expected, actual)。"""
        creating = expected_revision is None or expected_revision == 0
        if creating:
            rec = ToolConfig(
                user_sub=user_sub, tool_id=tool_id, key=key, value=value,
                schema_version=schema_version, updated_by_device=updated_by_device,
                revision=1, created_at=utcnow(), updated_at=utcnow(),
            )
            self.session.add(rec)
            try:
                async with self.session.begin_nested():
                    await self.session.flush()
            except IntegrityError:
                # 唯一约束冲突：SAVEPOINT 已回滚本次插入；整体回滚后在新事务里
                # 查当前 revision（供客户端精确 CAS）
                await self.session.rollback()
                current = await self.get_any(user_sub, tool_id, key)
                raise ConflictError(
                    "record already exists", expected=0,
                    actual=int(current.revision) if current else 0,
                ) from None
            await self.session.refresh(rec)
            return rec

        result = await self.exec_write(
            update(ToolConfig)
            .where(ToolConfig.user_sub == user_sub, ToolConfig.tool_id == tool_id,
                   ToolConfig.key == key, ToolConfig.revision == int(expected_revision),
                   ToolConfig.deleted_at.is_(None))
            .values(value=value, schema_version=schema_version,
                    updated_by_device=updated_by_device,
                    revision=ToolConfig.revision + 1, updated_at=utcnow()),
            "put.cas")
        if result.rowcount:
            rec = await self.get(user_sub, tool_id, key)
            assert rec is not None  # 刚更新成功，行必在
            return rec
        # CAS 未命中：区分「版本冲突」与「不存在」
        current = await self.get_any(user_sub, tool_id, key)
        if current is None or current.deleted_at is not None:
            raise NotFoundError(f"{tool_id}/{key} not found")
        raise ConflictError(
            "revision conflict",
            expected=int(expected_revision), actual=int(current.revision),
        )

    async def soft_delete(self, user_sub: str, tool_id: str, key: str,
                          expected_revision: int | None) -> ToolConfig:
        """软删除（乐观锁）。不存在/已删除/版本不符 → NotFoundError / ConflictError。"""
        if expected_revision is None:
            raise ConflictError("delete requires expected_revision",
                                expected=-1, actual=-1)
        result = await self.exec_write(
            update(ToolConfig)
            .where(ToolConfig.user_sub == user_sub, ToolConfig.tool_id == tool_id,
                   ToolConfig.key == key, ToolConfig.revision == int(expected_revision),
                   ToolConfig.deleted_at.is_(None))
            .values(deleted_at=utcnow(), revision=ToolConfig.revision + 1,
                    updated_at=utcnow()),
            "soft_delete.cas")
        if result.rowcount:
            rec = await self.get_any(user_sub, tool_id, key)
            assert rec is not None
            return rec
        current = await self.get_any(user_sub, tool_id, key)
        if current is None:
            raise NotFoundError(f"{tool_id}/{key} not found")
        if current.deleted_at is not None:
            raise NotFoundError(
                f"{tool_id}/{key} not found or already deleted (revision={current.revision})")
        raise ConflictError(
            "revision conflict",
            expected=int(expected_revision), actual=int(current.revision),
        )

    # ------------------------------------------------------------------ 视图
    @staticmethod
    def to_public(rec: ToolConfig) -> dict[str, Any]:
        """对外形状：不含内部行 id 与归属 user_sub，时间 ISO Z 字符串。"""
        return {
            "tool_id": rec.tool_id,
            "key": rec.key,
            "value": rec.value,
            "revision": int(rec.revision),
            "schema_version": int(rec.schema_version),
            "updated_by_device": rec.updated_by_device,
            "created_at": _iso(rec.created_at) or "",
            "updated_at": _iso(rec.updated_at) or "",
            "deleted_at": _iso(rec.deleted_at),
        }


def _iso(value: datetime | None) -> str | None:
    """aware UTC datetime -> 'Z' 结尾 ISO 字符串（与 models.iso_utc 语义一致）。"""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return (value.astimezone(timezone.utc)
            .isoformat(timespec="microseconds").replace("+00:00", "Z"))
