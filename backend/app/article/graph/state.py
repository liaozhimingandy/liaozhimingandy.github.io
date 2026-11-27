"""工作流状态定义：ArticleState TypedDict + 审核决定常量。

从原 app/article/llm.py 原样迁移（字段与语义零改动）。
提示词外置在 article/prompt/ 目录，节点函数见 nodes.py。
"""

from typing import List, TypedDict

# 审核决定的合法取值：通过 / 修改（仅大纲）/ 拒绝
REVIEW_PASS = "pass"
REVIEW_MODIFY = "modify"
REVIEW_REJECT = "reject"


class ArticleState(TypedDict):
    event_title: str               # 事件标题（聚合事件输出）
    event_summary: str             # 事件摘要
    source_contents: List[str]     # 已采集的正文素材（来自 news 表）
    source_urls: List[str]         # 溯源链接列表
    need_review: bool              # 是否需要人工审核（False：大纲/终审自动通过）
    outline: str                   # AI 生成大纲
    outline_review: str            # 人工大纲审核结果：pass / reject / modify
    modify_suggest: str            # 人工修改意见
    draft: str                     # 母稿
    multi_platform: dict           # 多平台版本：公众号/百家/头条/小红书/口播/标题组/封面
    check_report: str              # 自动质检报告（幻觉、风险）
    final_review: str              # 人工终审：pass / reject
    final_article: str             # 定稿
