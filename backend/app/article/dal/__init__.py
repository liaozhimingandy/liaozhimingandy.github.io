"""article 数据访问层：BaseDAO 基类 + 各表 DAO。"""

from .article import (  # noqa: F401
    ArticleDAO,
    EventDAO,
    NewsDAO,
    RelDAO,
    TaskDAO,
    TopicDAO,
)
from .base import BaseDAO, PageResult  # noqa: F401
