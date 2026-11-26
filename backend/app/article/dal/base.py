"""article DAL 基类：BaseDAO 已上移到 core（全项目共享），此文件保持兼容导入。"""

from app.core.dal_base import BaseDAO, PageResult  # noqa: F401
