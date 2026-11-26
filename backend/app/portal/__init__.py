"""Also Apps 门户包：SQLModel 模型 + DAL + 服务层。

分层：portal_api.py / portal_admin_api.py / configs.py（路由层）
    -> service.PortalService / ConfigService（事务出口）
    -> dal/*DAO -> SQLModel -> DB

表：portal_apps / app_categories / application_categories /
    user_app_favorites / user_app_recent_visits / tool_configs
建表走 SQLModel.metadata.create_all（core.database.init_db），不写 DDL 文件。
"""

from .service import ConfigService, PortalService, ToolRecord  # noqa: F401
