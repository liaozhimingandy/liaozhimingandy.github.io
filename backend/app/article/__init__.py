"""自媒体热点文章流水线包。

模块职责（采集/聚合/生成三阶段解耦，数据层统一走 SQLModel + core.database）：
    collector.py       采集：微博/百度热搜 -> SearXNG -> 正文/图片入库（定时/手动）
    cluster.py         聚合：SimHash + 向量把 pending topic 合并成 event（定时执行）
    llm.py             生成：LangGraph 工作流，按选中 event 生成文章（API 触发）
    scheduler.py       调度：采集/聚合两个 asyncio 周期任务，间隔可配
    service.py         服务层：素材组装、任务登记、事务边界（供 API 路由调用）
    models.py          领域模型：SQLModel 表模型（建表走 create_all）+ Pydantic 视图
    dal/               数据访问层：BaseDAO 泛型基类 + 各表 DAO（只 flush 不 commit）
    image_store.py     图片落盘：候选提取、过滤校验、下载保存
    prompt_manager.py  提示词加载：prompt/<func>/{system,user}.md
    pipeline.py        命令行编排：--stage collect|cluster|all

分层：api（../article_api.py）-> service（事务出口）-> dal（DAO）-> SQLModel。
运行约束：包内一律相对导入，须以 python -m app.article.xxx 方式运行。
"""
