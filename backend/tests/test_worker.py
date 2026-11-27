"""独立 worker 进程与 GraphService 门面测试。

覆盖：
    - GraphService 门面：方法委托到 runner 模块属性（patch 生效）；
    - 任务表队列协议：TaskDAO.claim CAS 领取、list_claimable 心跳过滤；
    - worker 领取后的规划（_plan_task）：审批决定消费 / 审批卡还原 /
      断点续跑 / 从头跑首段 / 素材缺失失败；
    - worker 模式下的 API 语义：generate 入队不执行、review 写决定、
      retry 重新入队、recover 让位给 worker；
    - run_generation_segment 线程池执行与心跳上报。

数据层与 test_article 相同：SQLite 内存引擎，不依赖真实 LLM/Postgres。
"""

from __future__ import annotations

import asyncio
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from app.core import database
from app.article import service, worker
from app.article.dal import EventDAO, NewsDAO, RelDAO, TaskDAO
from app.article.graph import service as graph_service_module
from app.article.graph.service import GraphService, get_graph_service
from app.article.models import ArticleEvent, ArticleNews


def _use_memory_db() -> None:
    database.use_memory_engine()
    asyncio.run(database.init_tables())


def _dispose_memory_db() -> None:
    asyncio.run(database.dispose_engine())


async def _aseed_material_event() -> int:
    async with database.session_scope() as session:
        event = ArticleEvent(
            event_title="worker 测试事件", event_summary="摘要",
            total_score=10, status="pending",
            source_urls=["https://example.com/a"], simhash="w1",
        )
        session.add(event)
        await session.flush()
        news = ArticleNews(
            hot_topic="worker 测试事件", hot_source="baidu", hot_score=1,
            news_url="https://example.com/a", url_key="https://example.com/a",
            title="标题", text="正文" * 100,
        )
        session.add(news)
        await session.flush()
        await RelDAO(session).link(int(event.id or 0), [int(news.id or 0)])
        return int(event.id or 0)


async def _aclear_tasks() -> None:
    await service._clear_tasks()


def _paused_result(stage: str = "outline", last_node: str = "generate_outline") -> dict:
    return {"status": "paused", "state": {}, "last_node": last_node,
            "stage": stage,
            "interrupt": {"stage": stage, "title": "审核",
                          "content": "待审内容", "options": ["同意", "拒绝"]}}


# --------------------------------------------------------------------------- #
# GraphService 门面
# --------------------------------------------------------------------------- #

class TestGraphService(unittest.TestCase):
    """GraphService 应把调用委托到 runner 模块属性（保持测试 patch 点不变）。"""

    def test_delegates_to_runner(self) -> None:
        svc = GraphService()
        with mock.patch("app.article.graph.runner.run_graph_step",
                        return_value={"status": "done"}) as p_step, \
             mock.patch("app.article.graph.runner.has_checkpoint",
                        return_value=True), \
             mock.patch("app.article.graph.runner.pending_interrupt",
                        return_value={"stage": "outline"}), \
             mock.patch("app.article.graph.runner.resume_command",
                        return_value="CMD") as p_cmd, \
             mock.patch("app.article.graph.runner.initial_state_from_material",
                        return_value={"event_title": "x"}) as p_init:
            self.assertEqual(svc.run_step({"a": 1}, "t1"), {"status": "done"})
            p_step.assert_called_once_with({"a": 1}, "t1")
            self.assertTrue(svc.has_checkpoint("t1"))
            self.assertEqual(svc.pending_interrupt("t1"), {"stage": "outline"})
            self.assertEqual(svc.resume_command("pass", "改一下"), "CMD")
            p_cmd.assert_called_once_with("pass", "改一下")
            self.assertEqual(svc.initial_state({"a": 1}, need_review=False),
                             {"event_title": "x"})

    def test_singleton(self) -> None:
        self.assertIs(get_graph_service(), get_graph_service())

    def test_model_exposed(self) -> None:
        self.assertTrue(get_graph_service().model)  # 与 graph/config.LLM_MODEL 同源


# --------------------------------------------------------------------------- #
# 任务表队列协议：claim CAS / list_claimable
# --------------------------------------------------------------------------- #

class TestClaimProtocol(unittest.IsolatedAsyncioTestCase):

    def setUp(self) -> None:
        _use_memory_db()
        self.addCleanup(_dispose_memory_db)
        self.addCleanup(lambda: asyncio.run(_aclear_tasks()))

    async def _seed_task(self, status: str = "queued", thread_id: str = "t-1",
                         heartbeat: str = "") -> str:
        task = await service._register_task(1, "标题", thread_id=thread_id)
        fields: dict = {"status": status}
        if status == "running":
            fields.update({"started_at": service._now(), "heartbeat_at": heartbeat})
        await service._update_task(task.task_id, **fields)
        return task.task_id

    async def test_claim_is_cas(self) -> None:
        task_id = await self._seed_task()
        async with database.session_scope() as session:
            dao = TaskDAO(session)
            ok = await dao.claim(task_id, "w-1", service._now())
            await session.commit()
            self.assertTrue(ok)
            # 状态已变 running：再以 queued 抢占必然失败（CAS 裁决）
            ok2 = await dao.claim(task_id, "w-2", service._now())
            self.assertFalse(ok2)

        snap = await service._get_task_snapshot(task_id)
        self.assertEqual(snap.status, "running")
        self.assertEqual(snap.claimed_by, "w-1")
        self.assertTrue(snap.heartbeat_at)

    async def test_list_claimable_filters_by_heartbeat(self) -> None:
        fresh = await self._seed_task(thread_id="t-fresh")
        stale = await self._seed_task(status="running", thread_id="t-stale",
                                      heartbeat=worker._iso_minus(3600))
        heartbeat_empty = await self._seed_task(status="running", thread_id="t-empty")
        await self._seed_task(status="done", thread_id="t-done")
        await self._seed_task(status="waiting_approval", thread_id="t-wait")

        async with database.session_scope() as session:
            rows = await TaskDAO(session).list_claimable(worker._iso_minus(900))
        ids = {r.task_id for r in rows}
        self.assertIn(fresh, ids)             # queued 可领
        self.assertIn(stale, ids)             # 心跳超时的 running 可接管
        self.assertIn(heartbeat_empty, ids)   # 无心跳的 running（历史遗留）可接管
        self.assertNotIn("t-done", ids)
        self.assertNotIn("t-wait", ids)
        self.assertTrue(all(r.status in ("queued", "running") for r in rows))


# --------------------------------------------------------------------------- #
# worker 领取后的规划（_plan_task）
# --------------------------------------------------------------------------- #

class TestPlanTask(unittest.IsolatedAsyncioTestCase):

    def setUp(self) -> None:
        _use_memory_db()
        self.addCleanup(_dispose_memory_db)
        self.addCleanup(lambda: asyncio.run(_aclear_tasks()))
        self.w = worker.ArticleWorker(concurrency=1)
        self.addCleanup(self.w.pool.shutdown, wait=True)

    async def _seed(self, thread_id: str = "t-plan", need_review: bool = True,
                    decision: str = "", status: str = "queued") -> str:
        event_id = await _aseed_material_event()
        task = await service._register_task(event_id, "标题", thread_id=thread_id,
                                            need_review=need_review)
        fields: dict = {"status": status}
        if decision:
            fields["review_decision"] = decision
        await service._update_task(task.task_id, **fields)
        return task.task_id

    async def test_decision_consumed_as_resume(self) -> None:
        task_id = await self._seed(decision="pass")
        with mock.patch("app.article.graph.runner.has_checkpoint", return_value=True), \
             mock.patch("app.article.graph.runner.pending_interrupt",
                        return_value={"stage": "outline"}), \
             mock.patch("app.article.graph.runner.resume_command",
                        return_value="RESUME-CMD") as p_cmd:
            action, payload = await self.w._plan_task(task_id)
        self.assertEqual(action, "resume")
        self.assertEqual(payload["command"], "RESUME-CMD")
        self.assertTrue(payload["thread_id"])
        p_cmd.assert_called_once_with("pass", "")

    async def test_stale_decision_cleared_then_continue(self) -> None:
        task_id = await self._seed(decision="pass")
        with mock.patch("app.article.graph.runner.has_checkpoint", return_value=True), \
             mock.patch("app.article.graph.runner.pending_interrupt",
                        return_value=None):
            action, payload = await self.w._plan_task(task_id)
        self.assertEqual(action, "continue")
        self.assertIsNone(payload)
        snap = await service._get_task_snapshot(task_id)
        self.assertEqual(snap.review_decision, "")  # 失效决定已清空

    async def test_interrupt_without_decision_restores_review(self) -> None:
        task_id = await self._seed(thread_id="t-rev")
        with mock.patch("app.article.graph.runner.has_checkpoint", return_value=True), \
             mock.patch("app.article.graph.runner.pending_interrupt",
                        return_value={"stage": "final", "title": "终审"}):
            action, payload = await self.w._plan_task(task_id)
        self.assertEqual(action, "review")
        self.assertEqual(payload["stage"], "final")
        self.assertEqual(payload["_thread_id"], "t-rev")

    async def test_no_checkpoint_plans_fresh_initial_state(self) -> None:
        task_id = await self._seed(thread_id="t-fresh2", need_review=False)
        with mock.patch("app.article.graph.runner.has_checkpoint", return_value=False):
            action, payload = await self.w._plan_task(task_id)
        self.assertEqual(action, "fresh")
        self.assertEqual(payload["event_title"], "worker 测试事件")
        self.assertFalse(payload["need_review"])

    async def test_missing_material_fails(self) -> None:
        task = await service._register_task(99999, "无素材", thread_id="t-none")
        with mock.patch("app.article.graph.runner.has_checkpoint", return_value=False):
            action, payload = await self.w._plan_task(task.task_id)
        self.assertEqual(action, "fail")
        self.assertIn("素材", str(payload))


# --------------------------------------------------------------------------- #
# worker 领取执行（claim -> plan -> segment 的端到端编排）
# --------------------------------------------------------------------------- #

class TestWorkerRunClaimed(unittest.IsolatedAsyncioTestCase):

    def setUp(self) -> None:
        _use_memory_db()
        self.addCleanup(_dispose_memory_db)
        self.addCleanup(lambda: asyncio.run(_aclear_tasks()))
        self.w = worker.ArticleWorker(concurrency=1)
        self.addCleanup(self.w.pool.shutdown, wait=True)

    async def test_fresh_task_runs_to_waiting_approval(self) -> None:
        event_id = await _aseed_material_event()
        task = await service._register_task(event_id, "标题", thread_id="t-e2e")
        with mock.patch("app.article.graph.runner.run_graph_step",
                        return_value=_paused_result()) as p_step, \
             mock.patch("app.article.graph.runner.has_checkpoint",
                        return_value=False):
            await self.w._run_claimed(task.task_id, "queued")

        snap = await service._get_task_snapshot(task.task_id)
        self.assertEqual(snap.status, "waiting_approval")
        self.assertEqual(snap.review_stage, "outline")
        self.assertEqual(snap.claimed_by, self.w.worker_id)
        self.assertTrue(snap.heartbeat_at)
        self.assertTrue(snap.review_content)
        # 首段输入：完整 initial state（need_review 默认 True）
        args, _ = p_step.call_args
        self.assertEqual(args[0]["event_title"], "worker 测试事件")
        self.assertTrue(args[0]["need_review"])

    async def test_resume_decision_runs_segment(self) -> None:
        # 审批后 API 已把任务置回 queued 并记录决定（见 TestWorkerModeApi），
        # worker 以 queued 领取、消费决定、恢复执行
        task = await service._register_task(1, "标题", thread_id="t-resume")
        await service._update_task(task.task_id, status="queued",
                                   review_decision="modify", review_suggest="换个角度")
        seen: list = []

        async def _fake_segment(task_id, step_input, **kwargs):
            seen.append((task_id, step_input, kwargs))
            return service.TASK_STATUS_RUNNING

        with mock.patch("app.article.graph.runner.pending_interrupt",
                        return_value={"stage": "outline"}), \
             mock.patch("app.article.graph.runner.has_checkpoint", return_value=True), \
             mock.patch("app.article.graph.runner.resume_command",
                        return_value="RESUME-CMD"), \
             mock.patch.object(service, "run_generation_segment",
                               side_effect=_fake_segment):
            await self.w._run_claimed(task.task_id, "queued")

        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][1], "RESUME-CMD")
        # 决定已消费清空；worker 线程池被注入执行段
        snap = await service._get_task_snapshot(task.task_id)
        self.assertEqual(snap.review_decision, "")
        self.assertEqual(seen[0][2].get("executor"), self.w.pool)
        self.assertFalse(seen[0][2].get("serialize", True))

    async def test_fail_action_marks_task_failed(self) -> None:
        task = await service._register_task(99999, "无素材", thread_id="t-fail")
        with mock.patch("app.article.graph.runner.has_checkpoint", return_value=False):
            await self.w._run_claimed(task.task_id, "queued")
        snap = await service._get_task_snapshot(task.task_id)
        self.assertEqual(snap.status, "failed")
        self.assertIn("素材", snap.error)

    async def test_claim_race_loser_skips(self) -> None:
        """被其他 worker 抢先领取的任务直接放弃，不重复执行。"""
        task = await service._register_task(1, "标题", thread_id="t-race")
        async with database.session_scope() as session:
            await TaskDAO(session).claim(task.task_id, "w-other", service._now())
            await session.commit()
        called: list = []

        async def _fake_segment(*a, **kw):
            called.append(a)
            return service.TASK_STATUS_RUNNING

        with mock.patch.object(service, "run_generation_segment",
                               side_effect=_fake_segment):
            await self.w._run_claimed(task.task_id, "queued")
        self.assertEqual(called, [])


# --------------------------------------------------------------------------- #
# worker 模式下的 API 语义
# --------------------------------------------------------------------------- #

class TestWorkerModeApi(unittest.IsolatedAsyncioTestCase):

    def setUp(self) -> None:
        _use_memory_db()
        self.addCleanup(_dispose_memory_db)
        self.addCleanup(lambda: asyncio.run(_aclear_tasks()))
        patcher = mock.patch.object(service, "execution_mode",
                                    return_value=service.MODE_WORKER)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _ready(self) -> dict:
        return {"deps_ok": True, "deps_error": "", "api_key_set": True, "ready": True}

    async def test_generate_only_enqueues(self) -> None:
        event_id = await _aseed_material_event()
        executed: list = []

        async def _no_run(*a, **kw):
            executed.append(a)
            raise AssertionError("worker 模式下 API 进程不应执行任何段")

        with mock.patch.object(service, "generator_available", return_value=self._ready()), \
             mock.patch.object(service, "run_generation_segment", side_effect=_no_run):
            task = await service.generate_for_event(event_id)
            await asyncio.sleep(0)  # 若误创建后台协程，这里会触发断言
        self.assertEqual(task.status, "queued")
        self.assertEqual(executed, [])
        self.assertTrue(task.thread_id)

    async def test_review_records_decision(self) -> None:
        task = await service._register_task(1, "标题", thread_id="t-rv")
        await service._update_task(task.task_id, status="waiting_approval",
                                   review_stage="outline")
        snap = await service.resume_generation(task.task_id, "modify", "换个角度")
        self.assertEqual(snap.status, "queued")
        self.assertEqual(snap.review_decision, "modify")
        self.assertEqual(snap.review_suggest, "换个角度")
        self.assertEqual(snap.current_step, "review_submitted")

    async def test_retry_requeues(self) -> None:
        task = await service._register_task(1, "标题", thread_id="t-rt")
        await service._update_task(task.task_id, status="failed",
                                   error="boom", finished_at=service._now())
        snap = await service.retry_task(task.task_id)
        self.assertEqual(snap.status, "queued")
        self.assertEqual(snap.error, "")
        self.assertEqual(snap.finished_at, "")

    async def test_recover_defers_to_worker(self) -> None:
        task = await service._register_task(1, "标题", thread_id="t-rec")
        await service._update_task(task.task_id, status="running")
        count = await service.recover_stale_tasks()
        self.assertEqual(count, 0)
        snap = await service._get_task_snapshot(task.task_id)
        self.assertEqual(snap.status, "running")  # 未被 API 进程动过


# --------------------------------------------------------------------------- #
# run_generation_segment：线程池注入与心跳
# --------------------------------------------------------------------------- #

class TestSegmentExecutor(unittest.IsolatedAsyncioTestCase):

    def setUp(self) -> None:
        _use_memory_db()
        self.addCleanup(_dispose_memory_db)
        self.addCleanup(lambda: asyncio.run(_aclear_tasks()))
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-pool")
        self.addCleanup(self.pool.shutdown, wait=True)

    async def test_segment_runs_in_pool_and_reports_heartbeat(self) -> None:
        task = await service._register_task(1, "标题", thread_id="t-hb")
        ctx = {"thread_id": "t-hb", "material": mock.Mock(), "article_uuid": "u"}
        threads: list = []

        def _fake_step(step_input, thread_id):
            import threading
            threads.append(threading.current_thread().name)
            return _paused_result()

        with mock.patch.object(service, "_load_run_ctx",
                               new=mock.AsyncMock(return_value=ctx)), \
             mock.patch("app.article.graph.runner.run_graph_step",
                        side_effect=_fake_step):
            status = await service.run_generation_segment(
                task.task_id, {"x": 1}, executor=self.pool, serialize=False)

        self.assertEqual(status, service.TASK_STATUS_WAITING_APPROVAL)
        self.assertTrue(threads[0].startswith("test-pool"))
        snap = await service._get_task_snapshot(task.task_id)
        self.assertTrue(snap.heartbeat_at)                       # 心跳已上报
        self.assertEqual(snap.current_step, "generate_outline")  # 执行节点已记录

    async def test_default_path_unserialized_uses_global_lock(self) -> None:
        """inline 默认调用（不传参数）仍走全局串行锁 + 默认线程，行为不变。"""
        task = await service._register_task(1, "标题", thread_id="t-inline")
        ctx = {"thread_id": "t-inline", "material": mock.Mock(), "article_uuid": "u"}
        with mock.patch.object(service, "_load_run_ctx",
                               new=mock.AsyncMock(return_value=ctx)), \
             mock.patch("app.article.graph.runner.run_graph_step",
                        return_value=_paused_result()):
            status = await service.run_generation_segment(task.task_id, {"x": 1})
        self.assertEqual(status, service.TASK_STATUS_WAITING_APPROVAL)


if __name__ == "__main__":
    unittest.main()
