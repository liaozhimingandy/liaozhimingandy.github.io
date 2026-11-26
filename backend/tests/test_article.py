"""article 流水线测试：SQLModel 内存库上的 DAL、服务层、API 契约。

测试不依赖真实网络、真实 LLM 或真实 PostgreSQL：
    - 数据层用 SQLite 内存引擎（StaticPool 共享连接），
      建表走 core.database.init_tables()（SQLModel.metadata.create_all）；
    - 生成流程只测任务登记与错误语义，真实工作流由集成环境验证。
"""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from fastapi.testclient import TestClient
from app import runtime
from app.core import database
from app.core.database import get_session
from app.article import service
from app.article.dal import ArticleDAO, EventDAO, NewsDAO, RelDAO, TopicDAO
from app.article.models import ArticleEvent, ArticleNews
from main import app


# --------------------------------------------------------------------------- #
# 内存库装配助手
# --------------------------------------------------------------------------- #

def _use_memory_db() -> None:
    """切换到全新 SQLite 内存引擎并建表（同步封装，测试 setUp 用）。"""
    database.use_memory_engine()
    asyncio.run(database.init_tables())


def _dispose_memory_db() -> None:
    asyncio.run(database.dispose_engine())


async def _aseed_material_event(event_id: int | None = None) -> int:
    """造一个已聚合、带新闻素材的 event（模拟聚类产物），返回 event id。

    async 版本：供 IsolatedAsyncioTestCase 测试内直接 await
    （asyncio.run 不允许在运行中的事件循环里调用）。
    """
    async with database.session_scope() as session:
        event = ArticleEvent(
            event_title="测试事件",
            event_summary="测试摘要",
            total_score=100,
            score_gain=10,
            status="pending",
            source_urls=["https://example.com/a"],
            images=[{"img_url": "images/x/a.webp", "alt": ""}],
            simhash="12345",
        )
        session.add(event)
        await session.flush()
        if event_id is not None and int(event.id or 0) != event_id:
            raise AssertionError(f"内存库 event id 漂移：{event.id} != {event_id}")
        news = ArticleNews(
            hot_topic="测试事件", hot_source="baidu", hot_score=1,
            news_url="https://example.com/a",
            url_key="https://example.com/a",
            title="新闻标题", text="x" * 7000,
        )
        session.add(news)
        await session.flush()
        await RelDAO(session).link(int(event.id or 0), [int(news.id or 0)])
        return int(event.id or 0)


def _seed_material_event(event_id: int | None = None) -> int:
    """sync 版本：供纯同步测试（unittest.TestCase）在无事件循环时调用。"""
    return asyncio.run(_aseed_material_event(event_id))


# --------------------------------------------------------------------------- #
# DAL 契约（SQLite 内存库）
# --------------------------------------------------------------------------- #

class TestArticleDal(unittest.IsolatedAsyncioTestCase):
    """DAO 契约：热搜去重、新闻去重、文章版本、状态更新。"""

    async def asyncSetUp(self) -> None:
        database.use_memory_engine()
        await database.init_tables()

    async def asyncTearDown(self) -> None:
        await database.dispose_engine()

    async def test_save_topics_dedup(self) -> None:
        async with database.session_scope() as session:
            dao = TopicDAO(session)
            hot_list = [
                {"title": "热点A", "source": "baidu", "hot_score": 100},
                {"title": "热点A", "source": "baidu", "hot_score": 100},
                {"title": "热点B", "source": "weibo", "hot_score": 50},
            ]
            self.assertEqual(await dao.save_topics(hot_list), 2)
            self.assertEqual(await dao.save_topics(hot_list), 0)
            topics = await dao.list_pending()
            self.assertEqual({t.title for t in topics}, {"热点A", "热点B"})
            self.assertEqual(await dao.count_pending(), 2)

    async def test_insert_news_dedup_by_normalized_url(self) -> None:
        async with database.session_scope() as session:
            dao = NewsDAO(session)
            art = {
                "url": "https://example.com/news/1",
                "title": "测试新闻标题",
                "text": "正文内容",
                "hot_topic": "测试热点",
                "hot_source": "baidu",
                "hot_score": 12345,
            }
            self.assertTrue(await dao.insert_news(art))
            self.assertFalse(await dao.insert_news(art))
            variant = dict(art)
            variant["url"] = ("http://www.example.com/news/1/?utm_source=share"
                              "&spm=abc#top")
            # 规范化后同链接，也必须跳过
            self.assertFalse(await dao.insert_news(variant))
            self.assertTrue(await dao.is_collected(variant["url"]))

    async def test_article_versioning(self) -> None:
        async with database.session_scope() as session:
            dao = ArticleDAO(session)
            first = await dao.save_new_version({
                "event_id": 1, "event_title": "测试事件",
                "draft": "v1", "multi_platform": {"wechat": "公众号版"},
                "source_urls": ["https://example.com/a"],
                "images": [{"img_url": "images/x/a.webp", "alt": ""}],
                "model": "aim-1", "status": "review", "uuid": "u-1",
            })
            second = await dao.save_new_version({
                "event_id": 1, "event_title": "测试事件", "draft": "v2",
                "uuid": "u-2",
            })
            self.assertTrue(first > 0 and second > first)

            items = await dao.list_articles(event_id=1)
            self.assertEqual(len(items), 1)  # 默认只看当前版本
            self.assertEqual(items[0].id, second)
            self.assertTrue(items[0].is_current)

            history = await dao.list_articles(event_id=1, include_history=True)
            self.assertEqual(len(history), 2)

            detail = await dao.get_by_uuid("u-2")
            self.assertIsNotNone(detail)
            assert detail is not None
            self.assertEqual(detail.draft, "v2")
            self.assertEqual(detail.multi_platform, {})
            self.assertIsNone(await dao.get_by_uuid("nonexistent"))

    async def test_mark_status_unknown_event(self) -> None:
        async with database.session_scope() as session:
            self.assertFalse(
                await EventDAO(session).mark_status(99999, "done"))


# --------------------------------------------------------------------------- #
# 服务层：素材组装与生成结果落库
# --------------------------------------------------------------------------- #

class TestArticleServiceDb(unittest.IsolatedAsyncioTestCase):
    """ArticleService 与真实会话配合的行为。"""

    async def asyncSetUp(self) -> None:
        database.use_memory_engine()
        await database.init_tables()

    async def asyncTearDown(self) -> None:
        await database.dispose_engine()

    async def test_get_material_truncates_and_fills_urls(self) -> None:
        event_id = await _aseed_material_event()
        async with database.session_scope() as session:
            material = await service.ArticleService(session).get_material(event_id)
        self.assertIsNotNone(material)
        assert material is not None
        self.assertTrue(material.source_contents[0].endswith("……（正文已截断）"))
        self.assertEqual(material.source_urls, ["https://example.com/a"])

        async with database.session_scope() as session:
            self.assertIsNone(
                await service.ArticleService(session).get_material(888))

    async def test_save_generation_result_marks_event(self) -> None:
        event_id = await _aseed_material_event()
        material = None
        async with database.session_scope() as session:
            material = await service.ArticleService(session).get_material(event_id)
        assert material is not None

        async with database.session_scope() as session:
            svc = service.ArticleService(session)
            article_id = await svc.save_generation_result(
                material, thread_id="t-1", article_uuid="gen-uuid-1",
                state={"outline": "大纲", "draft": "初稿", "final_article": "定稿",
                       "final_review": "pass", "multi_platform": {}},
                model_name="aim-1",
            )
        self.assertTrue(article_id > 0)

        async with database.session_scope() as session:
            dao = ArticleDAO(session)
            saved = await dao.get_by_uuid("gen-uuid-1")
            self.assertIsNotNone(saved)
            assert saved is not None
            self.assertEqual(saved.final_article, "定稿")
            self.assertEqual(saved.status, "done")
            event = await EventDAO(session).get_by_id(event_id)
            assert event is not None
            self.assertEqual(event.status, "done")


# --------------------------------------------------------------------------- #
# 服务层：任务登记与并发语义（纯内存）
# --------------------------------------------------------------------------- #

class TestArticleServiceTasks(unittest.TestCase):
    """任务登记与并发语义（不启动真实生成协程）。"""

    def setUp(self) -> None:
        service._clear_tasks()
        self.addCleanup(service._clear_tasks)

    def test_register_update_list_ordering(self) -> None:
        task = service._register_task(1, "事件A")
        service._update_task(task.task_id, status=service.TASK_STATUS_RUNNING)
        tasks = service.list_tasks(limit=10)
        self.assertEqual(tasks[0].status, "running")
        self.assertEqual(tasks[0].event_id, 1)

    def test_task_in_progress_locks_event(self) -> None:
        task = service._register_task(7, "事件B")
        self.assertEqual(service._task_in_progress(7), task.task_id)
        service._update_task(task.task_id, status=service.TASK_STATUS_FAILED)
        self.assertEqual(service._task_in_progress(7), "")

    def test_prune_tasks_keeps_capacity(self) -> None:
        with mock.patch.object(service, "MAX_TASK_HISTORY", 3):
            for event_id in range(1, 6):
                service._register_task(event_id, f"事件{event_id}")
            self.assertEqual(len(service._TASKS), 3)
            self.assertNotIn(1, {t.event_id for t in service.list_tasks(10)})

    def test_generate_for_event_requires_availability(self) -> None:
        async def _call() -> None:
            with mock.patch.object(
                service, "generator_available",
                return_value={"ready": False, "deps_ok": True, "api_key_set": False,
                              "deps_error": ""},
            ):
                await service.generate_for_event(1)

        with self.assertRaises(RuntimeError) as ctx:
            asyncio.run(_call())
        self.assertIn("generator_unavailable", str(ctx.exception))

    def test_generate_for_event_unknown_event(self) -> None:
        _use_memory_db()
        self.addCleanup(_dispose_memory_db)

        async def _call() -> None:
            with mock.patch.object(
                service, "generator_available",
                return_value={"ready": True, "deps_ok": True, "api_key_set": True,
                              "deps_error": ""},
            ):
                await service.generate_for_event(999)

        with self.assertRaises(LookupError):
            asyncio.run(_call())

    def test_generate_for_event_busy(self) -> None:
        _use_memory_db()
        self.addCleanup(_dispose_memory_db)
        _seed_material_event()
        task = service._register_task(1, "测试事件")

        async def _call() -> None:
            with mock.patch.object(
                service, "generator_available",
                return_value={"ready": True, "deps_ok": True, "api_key_set": True,
                              "deps_error": ""},
            ):
                await service.generate_for_event(1)

        with self.assertRaises(RuntimeError) as ctx:
            asyncio.run(_call())
        self.assertIn("event_busy", str(ctx.exception))
        self.assertEqual(task.status, "queued")


# --------------------------------------------------------------------------- #
# REST 契约
# --------------------------------------------------------------------------- #

class TestArticleApi(unittest.TestCase):
    """REST 契约：话题、任务、文章、管理端手动触发。

    setUp 手动 runtime.wire(app) 装配鉴权与存储（不走 lifespan，避免启动
    调度任务）；article 会话用 dependency_overrides 指向 SQLite 内存引擎。
    """

    def setUp(self) -> None:
        runtime.wire(app)
        _use_memory_db()
        self.addCleanup(_dispose_memory_db)

        async def _override_session():
            async with database.session_factory()() as session:
                yield session

        app.dependency_overrides[get_session] = _override_session
        self.addCleanup(app.dependency_overrides.pop, get_session, None)
        service._clear_tasks()
        self.addCleanup(service._clear_tasks)
        self.client = TestClient(app)

    def test_topics_endpoint_shape(self) -> None:
        _seed_material_event()
        resp = self.client.get("/v1/articles/topics")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["total"], 1)
        item = body["items"][0]
        for key in ("event_id", "event_title", "event_summary",
                    "total_score", "status", "source_urls", "images", "generating"):
            self.assertIn(key, item)
        self.assertEqual(item["event_title"], "测试事件")

    def test_generate_rejects_invalid_body(self) -> None:
        resp = self.client.post("/v1/articles/generate", json={})
        self.assertEqual(resp.status_code, 422)

    def test_generate_unknown_event_maps_to_404(self) -> None:
        with mock.patch.object(
            service, "generator_available",
            return_value={"ready": True, "deps_ok": True, "api_key_set": True,
                          "deps_error": ""},
        ):
            resp = self.client.post("/v1/articles/generate",
                                    json={"event_id": 999},
                                    headers={"X-User-Sub": "tester"})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error"], "EVENT_NOT_FOUND")

    def test_generate_busy_maps_to_409(self) -> None:
        async def _raise(event_id):
            raise RuntimeError("event_busy: gen_x")

        with mock.patch.object(service, "generate_for_event",
                               side_effect=_raise):
            resp = self.client.post("/v1/articles/generate",
                                    json={"event_id": 3},
                                    headers={"X-User-Sub": "tester"})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["error"], "EVENT_GENERATING")

    def test_generate_unavailable_maps_to_503(self) -> None:
        async def _raise(event_id):
            raise RuntimeError("generator_unavailable: LLM_API_KEY 未配置")

        with mock.patch.object(service, "generate_for_event",
                               side_effect=_raise):
            resp = self.client.post("/v1/articles/generate",
                                    json={"event_id": 3},
                                    headers={"X-User-Sub": "tester"})
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["error"], "GENERATOR_UNAVAILABLE")

    def test_get_unknown_task_maps_to_404(self) -> None:
        resp = self.client.get("/v1/articles/tasks/missing")
        self.assertEqual(resp.status_code, 404)

    def test_article_detail_unknown_uuid_maps_to_404(self) -> None:
        resp = self.client.get("/v1/articles/00000000-0000-0000-0000-000000000000")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error"], "ARTICLE_NOT_FOUND")

    def test_scheduler_endpoint_fail_closed_without_admin(self) -> None:
        with mock.patch("app.config.portal_admin_subs", return_value=set()):
            resp = self.client.get("/v1/articles/scheduler")
        self.assertEqual(resp.status_code, 403)

    def test_scheduler_endpoint_with_admin(self) -> None:
        with mock.patch("app.config.portal_admin_subs",
                        return_value={"demo-admin"}):
            resp = self.client.get("/v1/articles/scheduler",
                                   headers={"X-User-Sub": "demo-admin"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        for key in ("enabled", "tasks", "interval_minutes",
                    "last_collect", "last_cluster"):
            self.assertIn(key, body)

    def test_manual_cluster_with_admin(self) -> None:
        from app.article import scheduler

        async def _ok() -> int:
            return 5

        with mock.patch("app.config.portal_admin_subs",
                        return_value={"demo-admin"}), \
             mock.patch.object(scheduler, "run_cluster_now", side_effect=_ok):
            resp = self.client.post("/v1/articles/admin/cluster",
                                    headers={"X-User-Sub": "demo-admin"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"ok": True, "pending_topics_before": 5})

    def test_manual_cluster_busy_maps_to_409(self) -> None:
        from app.article import scheduler

        async def _busy() -> int:
            raise RuntimeError("cluster_busy")

        with mock.patch("app.config.portal_admin_subs",
                        return_value={"demo-admin"}), \
             mock.patch.object(scheduler, "run_cluster_now", side_effect=_busy):
            resp = self.client.post("/v1/articles/admin/cluster",
                                    headers={"X-User-Sub": "demo-admin"})
        self.assertEqual(resp.status_code, 409)

    def test_literal_routes_take_priority_over_uuid(self) -> None:
        """/v1/articles/generator 是字面量路由，不能被 /{article_uuid} 吞掉。"""
        with mock.patch("app.config.portal_admin_subs",
                        return_value={"demo-admin"}):
            resp = self.client.get("/v1/articles/generator",
                                   headers={"X-User-Sub": "demo-admin"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        for key in ("ready", "deps_ok", "api_key_set", "require_admin"):
            self.assertIn(key, body)


if __name__ == "__main__":
    unittest.main()
