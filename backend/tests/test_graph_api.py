"""graph 调试/编排接口契约测试（SSE 流式、状态、快照、图结构）。

不依赖真实 LLM 与真实 Postgres：
    - LLM 用 nodes._invoke 的 fake 替身（与 test_article 的真实图测试同法）；
    - checkpointer 用 MemorySaver（patch builder.get_graph 返回本地编译图）。
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app import runtime
from app.article.graph import builder as graph_builder
from app.article.graph import nodes as graph_nodes
from app.article.graph import saver as graph_saver
from main import app


def _fake_invoke(system: str, user: str) -> str:
    """假 LLM：多平台返回合法 JSON，其余返回带提示词前缀的固定文案。"""
    if any(k in system for k in ("多平台", "公众号")):
        return ('{"official":"公","baijia":"百","toutiao":"头",'
                '"title_list":["标题1"]}')
    return "【假LLM】" + user[:20]


def _compile_memory_graph():
    """真实节点 + MemorySaver 的本地编译图（隔离 Postgres/文件依赖）。"""
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, StateGraph

    from app.article.graph.nodes import (
        auto_check, generate_draft, generate_multi_platform, generate_outline,
        human_final_review, human_review_outline, re_generate_outline,
        route_outline,
    )
    from app.article.graph.state import ArticleState

    b = StateGraph(ArticleState)
    for name, fn in (
        ("generate_outline", generate_outline),
        ("human_review_outline", human_review_outline),
        ("re_generate_outline", re_generate_outline),
        ("generate_draft", generate_draft),
        ("generate_multi_platform", generate_multi_platform),
        ("auto_check", auto_check),
        ("human_final_review", human_final_review),
    ):
        b.add_node(name, fn)
    b.set_entry_point("generate_outline")
    b.add_edge("generate_outline", "human_review_outline")
    b.add_conditional_edges("human_review_outline", route_outline, {
        "generate_draft": "generate_draft",
        "re_generate_outline": "re_generate_outline",
        END: END,
    })
    b.add_edge("re_generate_outline", "human_review_outline")
    b.add_edge("generate_draft", "generate_multi_platform")
    b.add_edge("generate_multi_platform", "auto_check")
    b.add_edge("auto_check", "human_final_review")
    b.add_edge("human_final_review", END)
    return b.compile(checkpointer=MemorySaver())


def _init_state(need_review: bool = True) -> dict:
    return {
        "event_title": "测试事件", "event_summary": "摘要",
        "source_contents": ["素材正文"], "source_urls": ["https://example.com"],
        "need_review": need_review,
        "outline": "", "outline_review": "", "modify_suggest": "",
        "draft": "", "multi_platform": {}, "check_report": "",
        "final_review": "", "final_article": "",
    }


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    """把 SSE 文本解析成 (event, data) 列表。"""
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event, data = "", None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event = line[7:].strip()
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        events.append((event, data))
    return events


class TestGraphApi(unittest.TestCase):
    """REST/SSE 契约：真实节点 + MemorySaver + 假 LLM。"""

    def setUp(self) -> None:
        runtime.wire(app)
        self.client = TestClient(app)
        self.graph = _compile_memory_graph()
        # patch 路由模块引用的 builder.get_graph 与 checkpointer 探测
        self.patches = [
            mock.patch.object(graph_builder, "get_graph", return_value=self.graph),
            mock.patch.object(graph_saver, "get_checkpointer",
                              return_value=self.graph.checkpointer),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_graph_schema_shape(self) -> None:
        res = self.client.get("/graph/graph-schema")
        self.assertEqual(res.status_code, 200)
        schema = res.json()["schema"]
        names = {n["id"] for n in schema["nodes"]}
        self.assertIn("generate_outline", names)
        self.assertIn("human_final_review", names)
        self.assertGreaterEqual(len(schema["edges"]), 7)

    def test_state_unknown_thread_404(self) -> None:
        res = self.client.post("/graph/state", json={
            "thread_id": "no-such-thread", "checkpoint_id": None})
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["error"], "THREAD_NOT_FOUND")

    def test_stream_mode_validation(self) -> None:
        # init_state 与 checkpoint_id 互斥
        res = self.client.post("/graph/stream", json={
            "thread_id": "t-x", "init_state": _init_state(),
            "checkpoint_id": "cp-1"})
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"], "INVALID_STREAM_MODE")
        # 两者都缺
        res = self.client.post("/graph/stream", json={"thread_id": "t-y"})
        self.assertEqual(res.status_code, 422)

    def test_stream_full_run_no_review(self) -> None:
        """need_review=False：SSE 依次推送 7 个节点更新，finish 带定稿。"""
        with mock.patch.object(graph_nodes, "_invoke", side_effect=_fake_invoke):
            res = self.client.post("/graph/stream", json={
                "thread_id": "t-sse-full", "init_state": _init_state(False)})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.headers["content-type"].startswith("text/event-stream"))
        events = _parse_sse(res.text)
        kinds = [e for e, _ in events]
        # 无 error；节点更新按图顺序出现；finish 收尾
        self.assertNotIn("error", kinds)
        nodes_hit = [d["node"] for e, d in events if e == "node_update"]
        self.assertEqual(nodes_hit, [
            "generate_outline", "human_review_outline", "generate_draft",
            "generate_multi_platform", "auto_check", "human_final_review",
        ])
        finish = next(d for e, d in events if e == "finish")
        self.assertEqual(finish["next"], [])
        self.assertTrue(finish["values"]["final_article"])
        self.assertEqual(finish["values"]["multi_platform"]["official"], "公")

    def test_stream_pause_then_update_state_and_resume(self) -> None:
        """画布工作流：SSE 停在审核断点 -> update-state 写审核结果 -> 快照续跑。"""
        with mock.patch.object(graph_nodes, "_invoke", side_effect=_fake_invoke):
            res = self.client.post("/graph/stream", json={
                "thread_id": "t-sse-hitl", "init_state": _init_state(True)})
        events = _parse_sse(res.text)
        kinds = [e for e, _ in events]
        self.assertNotIn("error", kinds)
        # finish：next 非空 => 停在 human_review_outline
        finish = next(d for e, d in events if e == "finish")
        self.assertEqual(finish["next"], ["human_review_outline"])

        # state 接口确认停在 interrupt 断点
        state_res = self.client.post("/graph/state", json={
            "thread_id": "t-sse-hitl", "checkpoint_id": None})
        self.assertEqual(state_res.status_code, 200)
        body = state_res.json()
        self.assertTrue(body["waiting_interrupt"])
        self.assertEqual(body["tasks"][0]["interrupts"][0]["stage"], "outline")

        # update-state：人工大纲审核通过
        upd = self.client.post("/graph/update-state", json={
            "thread_id": "t-sse-hitl", "checkpoint_id": None,
            "values": {"outline_review": "pass", "modify_suggest": ""}})
        self.assertEqual(upd.status_code, 200)
        self.assertEqual(upd.json()["values"]["outline_review"], "pass")

        # checkpoints：列表里能看到已产生的快照
        cps = self.client.get("/graph/checkpoints?thread_id=t-sse-hitl")
        self.assertEqual(cps.status_code, 200)
        self.assertGreaterEqual(cps.json()["total"], 1)
        checkpoint_id = cps.json()["items"][0]["checkpoint_id"]

        # 从快照续跑：resume 大纲审核，跑到终审断点再停
        with mock.patch.object(graph_nodes, "_invoke", side_effect=_fake_invoke):
            res2 = self.client.post("/graph/stream", json={
                "thread_id": "t-sse-hitl", "checkpoint_id": checkpoint_id,
                "resume": {"decision": "pass", "suggest": ""}})
        events2 = _parse_sse(res2.text)
        self.assertNotIn("error", [e for e, _ in events2])
        finish2 = next(d for e, d in events2 if e == "finish")
        self.assertEqual(finish2["next"], ["human_final_review"])
        self.assertEqual(finish2["values"]["outline_review"], "pass")

        # 再 resume 一次终审（从最新断点，不带 checkpoint_id）=> 跑完
        with mock.patch.object(graph_nodes, "_invoke", side_effect=_fake_invoke):
            res3 = self.client.post("/graph/stream", json={
                "thread_id": "t-sse-hitl",
                "resume": {"decision": "pass", "suggest": ""}})
        events3 = _parse_sse(res3.text)
        self.assertNotIn("error", [e for e, _ in events3])
        finish3 = next(d for e, d in events3 if e == "finish")
        self.assertEqual(finish3["next"], [])
        self.assertTrue(finish3["values"]["final_article"])

    def test_stream_error_event_on_failure(self) -> None:
        """节点抛异常 => SSE 推送 error 事件后正常结束（连接不悬死）。"""
        def boom(system, user):
            raise RuntimeError("LLM 网关不可达")

        with mock.patch.object(graph_nodes, "_invoke", side_effect=boom):
            res = self.client.post("/graph/stream", json={
                "thread_id": "t-sse-err", "init_state": _init_state(False)})
        events = _parse_sse(res.text)
        errors = [d for e, d in events if e == "error"]
        self.assertEqual(len(errors), 1)
        self.assertIn("RuntimeError", errors[0]["message"])
