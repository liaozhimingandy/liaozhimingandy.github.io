"""DAO 基础层（抽象基类）——全项目数据访问层的统一基准。

与参考项目 tuiwen 的 dal/base.py 同构，按本项目「单库无主从」简化：
    1. 通用 CRUD（get/create/update/delete/bulk）；
    2. 分页查询（limit/offset 收敛 + 总数统计）；
    3. 字段合法性校验（防止字段名拼错生成错误 SQL）；
    4. SQL 性能监控（慢查询埋点 + 异常日志）。
不负责：
    1. 业务逻辑（在 service）；
    2. 事务控制（本类只 flush 不 commit，出口统一在 service）；
    3. 权限判断（在 API 路由层）。

分层调用链：API / scheduler → Service → DAO → SQLModel → DB

子类契约（类定义阶段强制校验）：
    class TopicDAO(BaseDAO[ArticleTopic]):   # 从泛型实参自动推导 model
        ...
    或显式声明 model = ArticleTopic；两者都没有 → 类定义时抛 TypeError。

全局约定：
    1. 表模型主键字段名统一为 id（get_by_id / partial_update 依赖此约定）；
    2. 表模型必须声明 __tablename__，基类据此生成 logger 名。
"""

from __future__ import annotations

import time
from abc import ABC
from dataclasses import dataclass
from typing import Any, Generic, Sequence, TypeVar, cast, get_args, get_origin

from sqlalchemy import delete, exists, func, inspect, update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from .logger import logger

T = TypeVar("T")

# 慢 SQL 阈值（秒）；单条查询超过即告警
SLOW_QUERY_THRESHOLD = 0.5

# model -> 该模型全部列名（ORM 属性名）集合；模块级缓存（每个请求都会新建实例）
_MODEL_COLUMNS_CACHE: dict[type, frozenset[str]] = {}


def _model_columns(model: type) -> frozenset[str]:
    """取 column.key（ORM 属性名）而非 column.name（数据库列名），保证与 **filters 一致。"""
    cached = _MODEL_COLUMNS_CACHE.get(model)
    if cached is None:
        cached = frozenset(col.key for col in inspect(model).mapper.column_attrs)
        _MODEL_COLUMNS_CACHE[model] = cached
    return cached


def _infer_model_from_generic(cls: type) -> type | None:
    """从 `class XxxDAO(BaseDAO[YyyModel])` 的泛型实参推导 ORM 模型。"""
    for base in getattr(cls, "__orig_bases__", ()) or ():
        origin = get_origin(base)
        params = get_args(base)
        if origin is None or len(params) != 1:
            continue
        model = params[0]
        if not isinstance(model, type):
            continue  # 仍是 TypeVar 的泛型中间类，交由最终子类绑定
        if isinstance(origin, type) and issubclass(origin, BaseDAO):
            return model
    return None


@dataclass(slots=True)
class PageResult(Generic[T]):
    """分页结果：items 当前页数据；total 符合条件的总数（与分页无关）。"""

    items: list[T]
    total: int


class BaseDAO(ABC, Generic[T]):
    """DAO 抽象基类：只做通用 CRUD + 读性能埋点，具体表 SQL 放子类。

    会话策略：单 AsyncSession（本项目无主从分离）。所有写操作只 flush，
    commit/rollback 由上层（service）在事务边界统一调用。
    """

    # 子类绑定的 ORM 模型；由 __init_subclass__ 校验/推导
    model: type[T]

    # 单次查询最大返回数量（兜底防 limit=10**9 拉爆内存）
    MAX_LIMIT = 200

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """子类创建时校验契约，让配置错误在 import 阶段就暴露。"""
        super().__init_subclass__(**kwargs)
        if getattr(cls, "model", None) is None:
            inferred = _infer_model_from_generic(cls)
            if inferred is not None:
                cls.model = inferred
        # 自身仍是泛型中间类（带未绑定 TypeVar）→ 跳过，交由最终子类绑定
        if cls.__dict__.get("__parameters__", ()):
            return
        model = getattr(cls, "model", None)
        if model is None:
            raise TypeError(
                f"{cls.__name__} 必须绑定 ORM 模型："
                f"class {cls.__name__}(BaseDAO[XxxModel]) 或声明 model = XxxModel"
            )
        if not hasattr(model, "__tablename__"):
            raise TypeError(
                f"{cls.__name__}.model 必须是 SQLModel 表模型（需带 __tablename__），当前为 {model!r}"
            )

    def __init__(self, session: AsyncSession) -> None:
        model = getattr(type(self), "model", None)
        if model is None:
            raise TypeError(f"{type(self).__name__} 未绑定 ORM 模型，不能实例化")
        self.session = session
        self.logger = logger.bind(dao=model.__tablename__)
        self._model_columns = _model_columns(model)

    # ---------------------------------------------------------------- #
    # 基础能力
    # ---------------------------------------------------------------- #

    @property
    def table_name(self) -> str:
        return self.model.__tablename__

    def _validate_fields(self, data: dict[str, Any]) -> None:
        """校验字典的键是否真实存在于模型，防止拼错的字段名生成错误 SQL。"""
        if not data:
            return
        invalid = [name for name in data if name not in self._model_columns]
        if invalid:
            raise ValueError(f"{self.table_name} invalid fields: {sorted(invalid)}")

    def _safe_page(self, limit: int, offset: int) -> tuple[int, int]:
        """分页参数收敛：limit ∈ [1, MAX_LIMIT]，offset >= 0。"""
        raw_limit = int(limit)
        limit = min(max(raw_limit, 1), self.MAX_LIMIT)
        if limit != raw_limit:
            self.logger.warning(
                f"limit clamped table={self.table_name} request={raw_limit} -> {limit}"
            )
        return limit, max(int(offset), 0)

    # ---------------------------------------------------------------- #
    # SQL 执行 + 监控
    # ---------------------------------------------------------------- #

    async def _execute(self, stmt: Any, op: str):
        """执行语句并统一埋点；异常记日志后原样上抛，由上层决定响应。"""
        start = time.perf_counter()
        try:
            result = await self.session.exec(stmt)
        except Exception:
            self.logger.exception(
                f"database error table={self.table_name} op={op} "
                f"cost={time.perf_counter() - start:.3f}s"
            )
            raise
        cost = time.perf_counter() - start
        if cost >= SLOW_QUERY_THRESHOLD:
            self.logger.warning(
                f"slow query table={self.table_name} op={op} cost={cost:.3f}s"
            )
        return result

    async def exec_write(self, stmt: Any, op: str = "write") -> Any:
        """执行自定义 DML（UPDATE/DELETE），只执行不提交；DML 可取 .rowcount。"""
        start = time.perf_counter()
        try:
            result = await self.session.exec(stmt)
        except Exception:
            self.logger.exception(
                f"database error table={self.table_name} op={op} "
                f"cost={time.perf_counter() - start:.3f}s"
            )
            raise
        return result

    # ---------------------------------------------------------------- #
    # 查询
    # ---------------------------------------------------------------- #

    async def get_by_id(self, pk: Any) -> T | None:
        stmt = select(self.model).where(self.model.id == pk)  # type: ignore[attr-defined]
        result = await self._execute(stmt, "get_by_id")
        return result.first()

    async def get_one(self, **filters: Any) -> T | None:
        """按等值条件取第一条；需要确定性顺序时用 get_list(order_by=...)。"""
        self._validate_fields(filters)
        stmt = select(self.model).limit(1)
        for field, value in filters.items():
            stmt = stmt.where(getattr(self.model, field) == value)
        result = await self._execute(stmt, "get_one")
        return result.first()

    async def get_list(self, *, limit: int = 20, offset: int = 0,
                       order_by: Any = None, **filters: Any) -> list[T]:
        """条件列表查询；order_by 传排序表达式（如 desc(Model.id)）。"""
        self._validate_fields(filters)
        limit, offset = self._safe_page(limit, offset)
        stmt = select(self.model)
        for field, value in filters.items():
            stmt = stmt.where(getattr(self.model, field) == value)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        stmt = stmt.limit(limit).offset(offset)
        result = await self._execute(stmt, "get_list")
        return list(cast(list[T], result.all()))

    async def count(self, **filters: Any) -> int:
        self._validate_fields(filters)
        stmt = select(func.count()).select_from(self.model)
        for field, value in filters.items():
            stmt = stmt.where(getattr(self.model, field) == value)
        result = await self._execute(stmt, "count")
        return int(result.one())

    async def page(self, *, limit: int = 20, offset: int = 0,
                   order_by: Any = None, **filters: Any) -> PageResult[T]:
        """分页查询：get_list + count 两条 SQL，条件完全一致。"""
        items = await self.get_list(limit=limit, offset=offset, order_by=order_by, **filters)
        total = await self.count(**filters)
        return PageResult(items=items, total=total)

    async def exists(self, **filters: Any) -> bool:
        """存在性判断（比 count 轻量）。"""
        self._validate_fields(filters)
        inner = select(self.model.id)  # type: ignore[attr-defined]
        for field, value in filters.items():
            inner = inner.where(getattr(self.model, field) == value)
        result = await self._execute(select(exists(inner)), "exists")
        return bool(result.first())

    # ---------------------------------------------------------------- #
    # 写操作：只 flush 不 commit（事务出口在 service）
    # ---------------------------------------------------------------- #

    async def create(self, obj: T) -> T:
        """新增实体；flush + refresh 回填数据库生成字段（自增 id/默认值）。"""
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(self, obj: T) -> T:
        """完整对象更新（merge 按主键覆盖）。"""
        obj = await self.session.merge(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def partial_update(self, pk: Any, data: dict[str, Any]) -> T | None:
        """按主键部分更新；data 为空时直接返回当前实体。"""
        self._validate_fields(data)
        if not data:
            return await self.session.get(self.model, pk)
        stmt = (
            update(self.model)
            .where(self.model.id == pk)  # type: ignore[attr-defined]
            .values(**data)
            .execution_options(synchronize_session="fetch")
        )
        result = await self.session.exec(stmt)
        if result.rowcount == 0:
            return None
        return await self.session.get(self.model, pk)

    async def delete_by_id(self, pk: Any) -> bool:
        stmt = delete(self.model).where(self.model.id == pk)  # type: ignore[attr-defined]
        result = await self.session.exec(stmt)
        return bool(result.rowcount)

    async def bulk_create(self, objs: Sequence[T]) -> Sequence[T]:
        """批量新增（add_all + flush，不 commit）。"""
        if not objs:
            return objs
        self.session.add_all(list(objs))
        await self.session.flush()
        return objs

    # ---------------------------------------------------------------- #
    # 事务出口（仅供 service 层在事务边界调用）
    # ---------------------------------------------------------------- #

    async def commit(self) -> None:
        """提交当前写事务。一次业务操作完成后由 service 调用一次。"""
        await self.session.commit()

    async def rollback(self) -> None:
        """回滚当前写事务（业务异常时由 service 调用）。"""
        await self.session.rollback()
