"""article 流水线测试：SQLModel 内存库上的 DAL、服务层、API 契约。

测试不依赖真实网络、真实 LLM 或真实 PostgreSQL：
    - 数据层用 SQLite 内存引擎（StaticPool 共享连接），
      建表走 core.database.init_tables()（SQLModel.metadata.create_all）；
    - 生成流程只测任务登记与错误语义，真实工作流由集成环境验证。
"""

from __future__ import annotations

import asyncio
import os
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


async def _aseed_material_event(event_id: int | None = None,
                                images: list | None = None,
                                thumbnail: str = "") -> int:
    """造一个已聚合、带新闻素材的 event（模拟聚类产物），返回 event id。

    async 版本：供 IsolatedAsyncioTestCase 测试内直接 await
    （asyncio.run 不允许在运行中的事件循环里调用）。
    images/thumbnail：可选的素材图片与封面缩略图（配图链路测试用）。
    """
    async with database.session_scope() as session:
        event = ArticleEvent(
            event_title="测试事件",
            event_summary="测试摘要",
            total_score=100,
            score_gain=10,
            status="pending",
            source_urls=["https://example.com/a"],
            images=images if images is not None else [
                {"img_url": "images/x/a.webp", "alt": ""}],
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
            thumbnail=thumbnail or None,
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

    async def test_get_material_collects_thumbnails(self) -> None:
        """素材组装：news.thumbnail 收进 material.thumbnails（封面兜底候选）。"""
        event_id = await _aseed_material_event(thumbnail="images/x/thumb.jpg")
        async with database.session_scope() as session:
            material = await service.ArticleService(session).get_material(event_id)
        assert material is not None
        self.assertEqual(material.thumbnails, ["images/x/thumb.jpg"])

    async def test_save_generation_result_illustrates_images(self) -> None:
        """落库配图链路：素材有图时选封面、正文与文章类平台版本插图。"""
        event_id = await _aseed_material_event(images=[
            {"img_url": "images/x/a.webp", "alt": "现场照片"},
            {"img_url": "images/x/b.jpg", "alt": ""},
            {"img_url": "https://remote.example.com/c.jpg", "alt": "远程图不配"},
        ])
        async with database.session_scope() as session:
            material = await service.ArticleService(session).get_material(event_id)
        assert material is not None

        long_text = "\n\n".join(f"第{i}段。" for i in range(1, 7))
        async with database.session_scope() as session:
            svc = service.ArticleService(session)
            await svc.save_generation_result(
                material, thread_id="t-2", article_uuid="gen-uuid-2",
                state={
                    "outline": "大纲", "draft": "初稿",
                    "final_article": long_text, "final_review": "pass",
                    "multi_platform": {
                        "official": long_text, "script": "口播稿不动",
                        "title_list": ["标题1", "标题2"],
                    },
                },
                model_name="aim-1",
            )

        async with database.session_scope() as session:
            saved = await ArticleDAO(session).get_by_uuid("gen-uuid-2")
            assert saved is not None
            # 封面：第一张本地图（远程图不参与），转成站点根路径
            self.assertEqual(saved.cover_image, "/images/x/a.webp")
            # 正文插图：剩余一张本地图 b 均匀插入；a 已是封面不再出现
            self.assertIn("![](/images/x/b.jpg)", saved.final_article)
            self.assertNotIn("/images/x/a.webp", saved.final_article)
            self.assertNotIn("remote.example.com", saved.final_article)
            # 文章类平台版本同样插图；口播稿/标题组不动
            self.assertIn("/images/x/b.jpg", saved.multi_platform["official"])
            self.assertEqual(saved.multi_platform["script"], "口播稿不动")
            self.assertEqual(saved.multi_platform["title_list"], ["标题1", "标题2"])


class TestIllustrate(unittest.TestCase):
    """配图后处理：候选归一、封面选择、正文均匀插图（幂等）。"""

    def test_normalize_candidates_keeps_local_only(self) -> None:
        from app.article import illustrate

        candidates = illustrate.normalize_candidates(
            [
                {"img_url": "images/x/a.webp", "alt": "现场[照]片"},
                {"img_url": "https://remote.example.com/c.jpg", "alt": "远程图"},
                "images/x/d.png",                       # 字符串形式也接受
                "not-image.jpg",                        # 非本地图被过滤
                {"img_url": "images/x/a.webp", "alt": "重复"},
            ],
            ["images/x/thumb.jpg", "images/x/a.webp"],  # 缩略图兜底，重复去重
        )
        self.assertEqual(
            [(c["img_url"], c["alt"]) for c in candidates],
            [
                ("/images/x/a.webp", "现场 照 片"),
                ("/images/x/d.png", ""),
                ("/images/x/thumb.jpg", "封面图"),
            ],
        )

    def test_pick_cover(self) -> None:
        from app.article import illustrate

        cover, inline = illustrate.pick_cover([])
        self.assertIsNone(cover)
        self.assertEqual(inline, [])
        cover, inline = illustrate.pick_cover([{"img_url": "/images/a.jpg", "alt": ""}])
        self.assertEqual(cover, {"img_url": "/images/a.jpg", "alt": ""})
        self.assertEqual(inline, [])

    def test_insert_images_even_distribution(self) -> None:
        from app.article import illustrate

        text = "\n\n".join(f"P{i}" for i in range(1, 7))
        images = [{"img_url": "/images/1.jpg", "alt": "图一"},
                  {"img_url": "/images/2.jpg", "alt": ""}]
        out = illustrate.insert_images(text, images)
        lines = [b for b in out.split("\n\n")]
        self.assertEqual(
            lines,
            ["P1", "P2", "![图一](/images/1.jpg)", "P3",
             "P4", "![](/images/2.jpg)", "P5", "P6"],
        )

    def test_insert_images_is_idempotent(self) -> None:
        from app.article import illustrate

        text = "A\n\nB\n\nC"
        images = [{"img_url": "/images/1.jpg", "alt": "图"}]
        once = illustrate.insert_images(text, images)
        self.assertEqual(illustrate.insert_images(once, images), once)

    def test_insert_images_skips_code_blocks_and_empty_text(self) -> None:
        from app.article import illustrate

        self.assertEqual(illustrate.insert_images("", [{"img_url": "/i.jpg", "alt": ""}]), "")
        text = "A\n\n```py\n\ncode\n\n```\n\nB"
        out = illustrate.insert_images(text, [{"img_url": "/images/1.jpg", "alt": ""}])
        # 唯一可插图位置在 A 之后（代码块整体跳过）
        self.assertEqual(out, "A\n\n![](/images/1.jpg)\n\n```py\n\ncode\n\n```\n\nB")

    def test_illustrate_state_no_images(self) -> None:
        from app.article import illustrate

        state = {"final_article": "定稿", "multi_platform": {"official": "公众号版"}}
        out = illustrate.illustrate_state(state, [], [])
        self.assertEqual(out["cover_image"], "")
        self.assertEqual(out["final_article"], "定稿")
        self.assertEqual(out["multi_platform"]["official"], "公众号版")
        # 不改入参
        self.assertNotIn("cover_image", state)

    def test_illustrate_state_covers_only_when_single_image(self) -> None:
        from app.article import illustrate

        state = {"final_article": "定稿", "multi_platform": {}}
        out = illustrate.illustrate_state(
            state, [{"img_url": "images/x/a.webp", "alt": "封面"}], [])
        self.assertEqual(out["cover_image"], "/images/x/a.webp")
        self.assertEqual(out["final_article"], "定稿")  # 唯一的图做了封面，正文不重复


class TestBaiduSDataParsing(unittest.TestCase):
    """百度 s-data 里出现非标准 JSON 转义时仍能解析（Invalid \\escape 回归）。"""

    def test_illegal_backslash_escape_is_repaired(self) -> None:
        from app.article.collector import parse_baidu_s_data

        raw = (
            '{"data":{"cards":[{"content":['
            '{"word":"第一道菜 -\\-鹏城迎宾冷盘","hotScore":"123"},'
            '{"word":"合法 \\n \\u4e2d 文","hotScore":"10"},'
            '{"word":"","hotScore":"9"}'
            ']}]}}'
        )
        items = parse_baidu_s_data(raw)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "第一道菜 -\\-鹏城迎宾冷盘")
        self.assertEqual(items[0]["hot_score"], 123)
        self.assertEqual(items[1]["title"], "合法 \n 中 文")

    def test_already_valid_json_is_unchanged(self) -> None:
        from app.article.collector import parse_baidu_s_data

        raw = '{"data":{"cards":[{"content":[{"word":"正常标题","hotScore":5}]}]}}'
        self.assertEqual(parse_baidu_s_data(raw), [
            {"title": "正常标题", "source": "baidu", "hot_score": 5},
        ])


# --------------------------------------------------------------------------- #
# 服务层：任务登记与并发语义（纯内存）
# --------------------------------------------------------------------------- #

class TestArticleServiceTasks(unittest.IsolatedAsyncioTestCase):
    """任务登记与并发语义（任务已落库，用 SQLite 内存表隔离，不启动真实生成协程）。"""

    async def asyncSetUp(self) -> None:
        database.use_memory_engine()
        await database.init_tables()
        await service._clear_tasks()

    async def asyncTearDown(self) -> None:
        await database.dispose_engine()

    async def test_register_update_list_ordering(self) -> None:
        task = await service._register_task(1, "事件A")
        await service._update_task(task.task_id, status=service.TASK_STATUS_RUNNING)
        tasks = await service.list_tasks(limit=10)
        self.assertEqual(tasks[0].status, "running")
        self.assertEqual(tasks[0].event_id, 1)

    async def test_task_in_progress_locks_event(self) -> None:
        task = await service._register_task(7, "事件B")
        self.assertEqual(await service._task_in_progress(7), task.task_id)
        await service._update_task(task.task_id, status=service.TASK_STATUS_FAILED)
        self.assertEqual(await service._task_in_progress(7), "")

    async def test_prune_tasks_keeps_capacity(self) -> None:
        with mock.patch.object(service, "MAX_TASK_HISTORY", 3):
            for event_id in range(1, 6):
                await service._register_task(event_id, f"事件{event_id}")
            tasks = await service.list_tasks(10)
            self.assertEqual(len(tasks), 3)
            self.assertNotIn(1, {t.event_id for t in tasks})

    async def test_task_persists_in_table(self) -> None:
        """回归：任务状态必须落 article_generation_task 表，查表可见。"""
        from app.article.dal import TaskDAO

        task = await service._register_task(42, "落库事件", thread_id="t-42",
                                            article_uuid="u-42")
        async with database.session_scope() as session:
            row = await TaskDAO(session).get_by_task_id(task.task_id)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.event_id, 42)
        self.assertEqual(row.thread_id, "t-42")
        self.assertEqual(row.article_uuid, "u-42")
        self.assertEqual(row.status, service.TASK_STATUS_QUEUED)

    async def test_generate_for_event_requires_availability(self) -> None:
        with mock.patch.object(
            service, "generator_available",
            return_value={"ready": False, "deps_ok": True, "api_key_set": False,
                          "deps_error": ""},
        ):
            with self.assertRaises(RuntimeError) as ctx:
                await service.generate_for_event(1)
        self.assertIn("generator_unavailable", str(ctx.exception))

    async def test_generate_for_event_unknown_event(self) -> None:
        with mock.patch.object(
            service, "generator_available",
            return_value={"ready": True, "deps_ok": True, "api_key_set": True,
                          "deps_error": ""},
        ):
            with self.assertRaises(LookupError):
                await service.generate_for_event(999)

    async def test_generate_for_event_busy(self) -> None:
        await _aseed_material_event()
        task = await service._register_task(1, "测试事件")
        with mock.patch.object(
            service, "generator_available",
            return_value={"ready": True, "deps_ok": True, "api_key_set": True,
                          "deps_error": ""},
        ):
            with self.assertRaises(RuntimeError) as ctx:
                await service.generate_for_event(1)
        self.assertIn("event_busy", str(ctx.exception))
        self.assertEqual((await service.get_task(task.task_id)).status, "queued")

    async def test_waiting_approval_counts_as_in_progress(self) -> None:
        task = await service._register_task(9, "待审事件")
        await service._update_task(task.task_id,
                                   status=service.TASK_STATUS_WAITING_APPROVAL)
        self.assertEqual(await service._task_in_progress(9), task.task_id)

    async def test_apply_step_result_paused_writes_review_fields(self) -> None:
        task = await service._register_task(10, "大纲待审")
        ctx = {"thread_id": "t-x", "material": None, "article_uuid": "u-x"}
        status = await service._apply_step_result(task.task_id, {
            "status": "paused", "stage": "outline",
            "interrupt": {"title": "大纲审核", "content": "大纲正文",
                          "options": ["pass", "modify", "reject"]},
            "state": {},
        }, ctx)
        self.assertEqual(status, service.TASK_STATUS_WAITING_APPROVAL)
        snap = await service.get_task(task.task_id)
        self.assertEqual(snap.review_stage, "outline")
        self.assertEqual(snap.review_title, "大纲审核")
        self.assertEqual(snap.review_content, "大纲正文")
        self.assertEqual(snap.review_options, ["pass", "modify", "reject"])
        self.assertEqual(snap.thread_id, "t-x")
        self.assertEqual(snap.current_step, "outline")

    async def test_apply_step_result_error_marks_failed(self) -> None:
        task = await service._register_task(11, "失败事件")
        status = await service._apply_step_result(task.task_id, {
            "status": "error", "error_msg": "BoomError: x", "state": {},
        }, {})
        self.assertEqual(status, service.TASK_STATUS_FAILED)
        self.assertIn("BoomError", (await service.get_task(task.task_id)).error)

    async def test_recover_stale_resumes_running_keeps_waiting(self) -> None:
        """回归：启动恢复接续 running 任务（断点续跑），waiting_approval 保留等审批。"""
        running = await service._register_task(20, "中断任务", thread_id="t-run")
        await service._update_task(running.task_id, status=service.TASK_STATUS_RUNNING)
        waiting = await service._register_task(21, "待审任务")
        await service._update_task(waiting.task_id,
                                   status=service.TASK_STATUS_WAITING_APPROVAL)

        resumed: list[tuple[str, object]] = []

        async def _fake_segment(task_id, step_input):
            resumed.append((task_id, step_input))
            return service.TASK_STATUS_RUNNING

        with mock.patch.object(service, "_has_checkpoint",
                               new=mock.AsyncMock(return_value=True)), \
             mock.patch.object(service, "run_generation_segment",
                               side_effect=_fake_segment):
            count = await service.recover_stale_tasks()
        await asyncio.sleep(0)   # 让 create_task 的接续协程跑起来
        self.assertEqual(count, 1)
        # 有 checkpoint：传 None 从断点续跑，而不是标失败
        self.assertEqual(resumed[0], (running.task_id, None))
        self.assertEqual((await service.get_task(running.task_id)).status,
                         service.TASK_STATUS_RUNNING)
        self.assertEqual((await service.get_task(waiting.task_id)).status,
                         service.TASK_STATUS_WAITING_APPROVAL)

    async def test_recover_stale_restores_interrupt_as_waiting(self) -> None:
        """进程死在「已暂停等审核」与「状态写库」之间：重启后还原审批卡。"""
        task = await service._register_task(30, "中断在审核点", thread_id="t-int")
        await service._update_task(task.task_id, status=service.TASK_STATUS_RUNNING)
        interrupt = {"stage": "outline", "title": "大纲审核",
                     "content": "大纲内容", "options": ["pass", "modify"]}

        with mock.patch.object(service, "_has_checkpoint",
                               new=mock.AsyncMock(return_value=True)), \
             mock.patch("app.article.llm.pending_interrupt", return_value=interrupt):
            count = await service.recover_stale_tasks()
        self.assertEqual(count, 1)
        snap = await service.get_task(task.task_id)
        self.assertEqual(snap.status, service.TASK_STATUS_WAITING_APPROVAL)
        self.assertEqual(snap.review_stage, "outline")
        self.assertEqual(snap.review_title, "大纲审核")

    async def test_retry_task_resumes_from_checkpoint(self) -> None:
        """失败任务重试：有 checkpoint 时传 None 从报错节点续跑。"""
        task = await service._register_task(31, "失败任务", thread_id="t-fail")
        await service._update_task(task.task_id, status=service.TASK_STATUS_FAILED,
                                   error="OperationalError: server closed")
        resumed: list[tuple[str, object]] = []

        async def _fake_segment(task_id, step_input):
            resumed.append((task_id, step_input))
            return service.TASK_STATUS_RUNNING

        with mock.patch.object(service, "_has_checkpoint",
                               new=mock.AsyncMock(return_value=True)), \
             mock.patch.object(service, "run_generation_segment",
                               side_effect=_fake_segment):
            snap = await service.retry_task(task.task_id)
        self.assertEqual(snap.status, service.TASK_STATUS_RUNNING)
        self.assertEqual(resumed[0], (task.task_id, None))

    async def test_retry_task_rejects_non_failed(self) -> None:
        """只有 failed 任务可重试；运行中/待审/已完成拒绝。"""
        task = await service._register_task(32, "运行中任务")
        await service._update_task(task.task_id, status=service.TASK_STATUS_RUNNING)
        with self.assertRaises(RuntimeError):
            await service.retry_task(task.task_id)

    async def test_segment_retry_resumes_after_transient_error(self) -> None:
        """瞬时故障重试：第一次失败后改传 None 从 checkpoint 续跑。

        回归背景：Postgres 重启报 OperationalError: server closed the
        connection unexpectedly 时，任务不能直接标失败——要退避后从报错
        节点继续，重试耗尽才标失败。
        """
        task = await service._register_task(33, "重试任务", thread_id="t-retry")
        ctx = {"thread_id": "t-retry", "material": mock.Mock(), "article_uuid": "u"}
        inputs: list = []

        def _fake_graph_step(step_input, thread_id):
            inputs.append(step_input)
            if len(inputs) == 1:
                return {"status": "error", "state": {},
                        "error_msg": "OperationalError: server closed the connection"}
            return {"status": "paused", "stage": "outline",
                    "interrupt": {"stage": "outline", "title": "大纲审核"},
                    "last_node": "generate_outline", "state": {}}

        async def _fake_apply(task_id, result, ctx):
            return service.TASK_STATUS_WAITING_APPROVAL

        with mock.patch.object(service, "_load_run_ctx",
                               new=mock.AsyncMock(return_value=ctx)), \
             mock.patch.object(service, "_has_checkpoint",
                               new=mock.AsyncMock(return_value=True)), \
             mock.patch.object(service, "_apply_step_result",
                               side_effect=_fake_apply), \
             mock.patch("app.article.llm.run_graph_step",
                        side_effect=_fake_graph_step), \
             mock.patch("asyncio.sleep", new=mock.AsyncMock()):
            status = await service.run_generation_segment(task.task_id, {"x": 1})

        self.assertEqual(status, service.TASK_STATUS_WAITING_APPROVAL)
        self.assertEqual(len(inputs), 2)
        self.assertEqual(inputs[0], {"x": 1})
        # 第二次改传 None：从 checkpoint 续跑，而非从头重跑
        self.assertIsNone(inputs[1])


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
        # 任务表现已落库：清空走 async helper（内存库，无 psycopg 事件循环冲突）
        asyncio.run(service._clear_tasks())
        self.addCleanup(lambda: asyncio.run(service._clear_tasks()))
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
        async def _raise(event_id, need_review=None):
            raise RuntimeError("event_busy: gen_x")

        with mock.patch.object(service, "generate_for_event",
                               side_effect=_raise):
            resp = self.client.post("/v1/articles/generate",
                                    json={"event_id": 3},
                                    headers={"X-User-Sub": "tester"})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["error"], "EVENT_GENERATING")

    def test_generate_unavailable_maps_to_503(self) -> None:
        async def _raise(event_id, need_review=None):
            raise RuntimeError("generator_unavailable: LLM_API_KEY 未配置")

        with mock.patch.object(service, "generate_for_event",
                               side_effect=_raise):
            resp = self.client.post("/v1/articles/generate",
                                    json={"event_id": 3},
                                    headers={"X-User-Sub": "tester"})
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["error"], "GENERATOR_UNAVAILABLE")

    def test_review_rejects_invalid_decision(self) -> None:
        resp = self.client.post(
            "/v1/articles/tasks/t1/review",
            json={"decision": "maybe"},
            headers={"X-User-Sub": "tester"},
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["error"], "INVALID_REVIEW")

    def test_review_requires_suggest_for_modify(self) -> None:
        resp = self.client.post(
            "/v1/articles/tasks/t1/review",
            json={"decision": "modify", "suggest": "  "},
            headers={"X-User-Sub": "tester"},
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["error"], "REVIEW_SUGGEST_REQUIRED")

    def test_review_unknown_task_maps_to_404(self) -> None:
        async def _raise(*args):
            raise LookupError("任务不存在：t-missing")

        with mock.patch.object(service, "resume_generation", side_effect=_raise):
            resp = self.client.post(
                "/v1/articles/tasks/t-missing/review",
                json={"decision": "pass"},
                headers={"X-User-Sub": "tester"},
            )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error"], "TASK_NOT_FOUND")

    def test_review_not_waiting_maps_to_409(self) -> None:
        async def _raise(*args):
            raise RuntimeError("任务不在等待审核状态：done")

        with mock.patch.object(service, "resume_generation", side_effect=_raise):
            resp = self.client.post(
                "/v1/articles/tasks/t1/review",
                json={"decision": "pass"},
                headers={"X-User-Sub": "tester"},
            )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["error"], "TASK_NOT_WAITING")

    def test_review_success_returns_task(self) -> None:
        task = asyncio.run(service._register_task(5, "审核中"))
        asyncio.run(service._update_task(
            task.task_id, status=service.TASK_STATUS_RUNNING,
            review_stage="", thread_id="t-ok",
        ))

        async def _resume(task_id, decision, suggest=""):
            await service._update_task(task_id, status=service.TASK_STATUS_DONE)
            return await service.get_task(task_id)

        with mock.patch.object(service, "resume_generation", side_effect=_resume):
            resp = self.client.post(
                f"/v1/articles/tasks/{task.task_id}/review",
                json={"decision": "pass"},
                headers={"X-User-Sub": "tester"},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "done")

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

    def test_scheduler_loop_runs_first_round_after_start_delay(self) -> None:
        """调度器首轮必须在启动延迟后执行（Python 3.14 Event.wait 回归）。

        旧实现 `await _stop_event.wait()` / `wait(interval)` 在正常运行时
        永不超时（3.14 起后者直接 TypeError），导致到点不采集/不聚合。
        """
        from app.article import scheduler

        async def scenario() -> list[str]:
            calls: list[str] = []
            original_event = scheduler._stop_event

            async def fake_collect() -> dict:
                calls.append("collect")
                return {}

            scheduler._stop_event = asyncio.Event()
            try:
                with mock.patch("app.config.article_scheduler_start_delay_sec",
                                return_value=0.01), \
                     mock.patch.object(scheduler, "run_collect_now",
                                       side_effect=fake_collect):
                    task = asyncio.create_task(scheduler._loop("collect", 0.01))
                    await asyncio.sleep(0.1)
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            finally:
                scheduler._stop_event = original_event
            return calls

        calls = asyncio.run(scenario())
        self.assertGreaterEqual(len(calls), 2, "首轮与至少一个后续间隔都应实际执行")

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


class TestHitlSegmentedExecution(unittest.IsolatedAsyncioTestCase):
    """HITL 分段执行：用真实的带 interrupt 小图验证暂停/恢复状态机。"""

    async def asyncSetUp(self) -> None:
        database.use_memory_engine()
        await database.init_tables()
        await service._clear_tasks()

    async def asyncTearDown(self) -> None:
        await database.dispose_engine()

    async def test_run_graph_step_none_input_resumes_failed_node(self) -> None:
        """报错节点断点续跑：节点失败后传 None 重跑该节点，已完成节点不重复执行。

        LangGraph 在节点执行前落 checkpoint，节点中途失败时 checkpoint
        停在「该节点执行前」——None 输入即从那里续跑（服务重启/瞬时故障
        都靠这个机制从报错节点继续）。
        """
        from typing import TypedDict

        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.graph import END, START, StateGraph
        from app.article import llm

        class S(TypedDict):
            calls: int

        calls = {"n": 0}

        def flaky(state):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("OperationalError: server closed the connection")
            return {"calls": state["calls"] + 1}

        b = StateGraph(S)
        b.add_node("flaky", flaky)
        b.add_edge(START, "flaky")
        b.add_edge("flaky", END)
        graph = b.compile(checkpointer=MemorySaver())

        with mock.patch.object(llm, "get_graph", return_value=graph):
            r1 = llm.run_graph_step({"calls": 0}, "thread-flaky-1")
            self.assertEqual(r1["status"], "error")
            # 节点失败但 checkpoint 已落（停在节点执行前）
            self.assertTrue(llm.has_checkpoint("thread-flaky-1"))
            self.assertIsNone(llm.pending_interrupt("thread-flaky-1"))
            # None 输入 = 从 checkpoint 续跑，重跑失败的 flaky 节点
            r2 = llm.run_graph_step(None, "thread-flaky-1")
            self.assertEqual(r2["status"], "done")
            self.assertEqual(calls["n"], 2)

    async def test_llm_run_graph_step_pause_resume(self) -> None:
        from typing import TypedDict

        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.graph import END, START, StateGraph
        from langgraph.types import interrupt
        from app.article import llm

        class S(TypedDict):
            log: list

        def review(state):
            ans = interrupt({"stage": "outline", "title": "大纲审核",
                             "content": "大纲正文", "options": ["pass"]})
            return {"log": state["log"] + [ans["decision"]]}

        b = StateGraph(S)
        b.add_node("review", review)
        b.add_edge(START, "review")
        b.add_edge("review", END)
        graph = b.compile(checkpointer=MemorySaver())

        with mock.patch.object(llm, "get_graph", return_value=graph):
            r1 = llm.run_graph_step({"log": []}, "thread-hitl-1")
            self.assertEqual(r1["status"], "paused")
            self.assertEqual(r1["stage"], "outline")
            self.assertEqual(r1["interrupt"]["content"], "大纲正文")

            cmd = llm.resume_command("pass", "")
            r2 = llm.run_graph_step(cmd, "thread-hitl-1")
            self.assertEqual(r2["status"], "done")
            self.assertEqual(r2["state"]["log"], ["pass"])

    async def test_real_graph_two_stage_interrupt(self) -> None:
        """用真实编译的图（非 mock graph）验证两个审核节点都能 interrupt。

        回归 bug：审核节点漏 import interrupt 时，mock graph 测试全绿，
        但真实运行报 NameError，任务永远卡在 running。此测试直接触发真实节点。
        """
        from app.article import llm

        def fake_invoke(system: str, user: str) -> str:
            if any(k in system for k in ("多平台", "公众号")):
                return ('{"official":"公","baijia":"百","toutiao":"头",'
                        '"title_list":["标题1"]}')
            return "【假LLM】" + user[:20]

        material = {
            "id": 778, "event_title": "测试", "event_summary": "",
            "source_contents": ["素材"], "source_urls": [],
        }
        tid = "thread-real-778"
        with mock.patch.object(llm, "_invoke", side_effect=fake_invoke):
            r1 = llm.run_graph_step(llm.initial_state_from_material(material), tid)
            self.assertEqual(r1["status"], "paused")
            self.assertEqual(r1["stage"], "outline")

            r2 = llm.run_graph_step(llm.resume_command("pass", ""), tid)
            self.assertEqual(r2["status"], "paused")
            self.assertEqual(r2["stage"], "final")

            r3 = llm.run_graph_step(llm.resume_command("pass", ""), tid)
            self.assertEqual(r3["status"], "done")
            self.assertTrue(r3["state"].get("final_article"))

    async def test_need_review_false_runs_to_done_without_pause(self) -> None:
        """need_review=False（审核可配置关闭）：两个审核节点都自动通过，全程无 interrupt。

        回归背景：人工审核做成可配置后，关闭时必须真的跳过两个 interrupt，
        任务从 queued 直接跑完，前端不会再收到审批卡。
        """
        from app.article import llm

        def fake_invoke(system: str, user: str) -> str:
            if any(k in system for k in ("多平台", "公众号")):
                return ('{"official":"公","baijia":"百","toutiao":"头",'
                        '"title_list":["标题1"]}')
            return "【假LLM】" + user[:20]

        material = {
            "id": 779, "event_title": "免审测试", "event_summary": "",
            "source_contents": ["素材"], "source_urls": [],
        }
        tid = "thread-noreview-779"
        with mock.patch.object(llm, "_invoke", side_effect=fake_invoke):
            r = llm.run_graph_step(
                llm.initial_state_from_material(material, need_review=False), tid)
            self.assertEqual(r["status"], "done")
            self.assertTrue(r["state"].get("final_article"))
            # 自动通过路径：审核字段直接置 pass，而非挂起等待
            self.assertEqual(r["state"].get("outline_review"), "pass")
            self.assertEqual(r["state"].get("final_review"), "pass")


class TestGeneratorAvailability(unittest.TestCase):
    """生成能力判定：密钥必须以 Settings 为准，不能只看 os.environ。"""

    def test_key_from_settings_is_configured_even_without_env_var(self) -> None:
        """回归 bug：pydantic-settings 从 .env 读密钥但不写回 os.environ，
        旧实现用 os.getenv 判定会把已配置的密钥误判为未配置，导致一直返回 503。
        """
        fake_settings = mock.Mock()
        fake_settings.LLM_API_KEY = "sk-from-dotenv"
        env_without_key = {k: v for k, v in os.environ.items() if k != "LLM_API_KEY"}
        with mock.patch.dict(os.environ, env_without_key, clear=True), \
                mock.patch("app.article.service.get_settings", return_value=fake_settings):
            result = service.generator_available()
        self.assertTrue(result["api_key_set"])
        self.assertTrue(result["ready"])

    def test_blank_key_is_not_configured(self) -> None:
        fake_settings = mock.Mock()
        fake_settings.LLM_API_KEY = "   "
        with mock.patch("app.article.service.get_settings", return_value=fake_settings):
            result = service.generator_available()
        self.assertFalse(result["api_key_set"])
        self.assertFalse(result["ready"])


if __name__ == "__main__":
    unittest.main()
