"""Also Apps 门户包：SQLModel 模型 + DAL + 服务层。

分层：router.py / admin_router.py / configs_router.py（路由层，本包统一导出）
    -> service.PortalService / ConfigService（事务出口）
    -> dal/*DAO -> SQLModel -> DB

表：portal_apps / app_categories / application_categories /
    user_app_favorites / user_app_recent_visits / tool_configs
建表走 SQLModel.metadata.create_all（core.database.init_db），不写 DDL 文件。
"""

from .router import router  # noqa: F401  上一级统一导出的门户/用户路由
from .admin_router import router as admin_router  # noqa: F401  管理端路由
from .configs_router import router as configs_router  # noqa: F401  公共配置表路由
from .service import ConfigService, PortalService, ToolRecord  # noqa: F401
