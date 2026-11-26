"""Also Apps 门户契约测试（unittest 标准库 + FastAPI TestClient）。

覆盖任务验收项：
  新增/编辑/删除应用、发布下架、首页推荐配置、分类筛选、关键词搜索、
  收藏/取消、最近访问、匿名与登录浏览、私有应用拦截、非法 URL 校验、
  越权（指定他人身份无效）、管理员白名单 fail-closed、URL 安全。
测试不依赖真实 PG、真实 Logto 租户或真实时钟：数据层走 SQLite 内存引擎
（与生产共用同一套 SQLModel/DAL/Service 代码路径）。
"""

from __future__ import annotations

import unittest

from app.portal.models import ValidationError, validate_launch_url
from app.portal_ids import uuid7
from tests.helpers import (
    USER_A,
    USER_B,
    admin_headers,
    api_client,
    get_app_id_by_code,
    user_headers,
)


class TestPublicCatalog(unittest.TestCase):
    def test_anonymous_sees_only_published_public(self) -> None:
        with api_client() as c:
            res = c.get("/v1/portal/apps")
            self.assertEqual(res.status_code, 200)
            codes = set(a["code"] for a in res.json()["items"])
            self.assertEqual(codes, {"PUB", "AUTH"})  # DRAFT/PRIVATE 不可见

    def test_private_app_detail_hidden(self) -> None:
        with api_client() as c:
            self.assertEqual(c.get("/v1/portal/apps/PRIVATE").status_code, 404)
            self.assertEqual(c.get("/v1/portal/apps/DRAFT").status_code, 404)

    def test_keyword_search_covers_code_and_name(self) -> None:
        with api_client() as c:
            self.assertEqual(c.get("/v1/portal/apps/search?q=PUB").json()["total"], 1)
            self.assertEqual(c.get("/v1/portal/apps/search?q=公开").json()["total"], 1)
            self.assertEqual(c.get("/v1/portal/apps/search?q=nope").json()["total"], 0)

    def test_category_filter_and_query_params(self) -> None:
        with api_client() as c:
            res = c.get("/v1/portal/apps?category=ai")
            self.assertEqual(res.json()["total"], 0)  # 种子应用都不属于 ai
            res = c.get("/v1/portal/apps?category=all")
            self.assertEqual(res.json()["total"], 2)

    def test_pagination(self) -> None:
        with api_client() as c:
            res = c.get("/v1/portal/apps?page=1&page_size=1")
            self.assertEqual(len(res.json()["items"]), 1)
            self.assertEqual(res.json()["total"], 2)


class TestLaunch(unittest.TestCase):
    def test_published_app_launch_allowed(self) -> None:
        with api_client() as c:
            res = c.post("/v1/portal/apps/PUB/launch")
            self.assertTrue(res.json()["allowed"])
            self.assertEqual(res.json()["url"], "https://example.com/pub")

    def test_auth_required_app_needs_login(self) -> None:
        with api_client() as c:
            res = c.post("/v1/portal/apps/AUTH/launch")
            self.assertFalse(res.json()["allowed"])
            self.assertEqual(res.json()["reason"], "LOGIN_REQUIRED")
            res = c.post("/v1/portal/apps/AUTH/launch", headers=user_headers())
            self.assertTrue(res.json()["allowed"])

    def test_private_app_forbidden_even_logged_in(self) -> None:
        with api_client() as c:
            res = c.post("/v1/portal/apps/PRIVATE/launch", headers=user_headers())
            self.assertEqual(res.status_code, 403)

    def test_not_deployed_app_blocked(self) -> None:
        with api_client() as c:
            admin = admin_headers()
            c.post(
                "/v1/portal/admin/apps", headers=admin,
                json={"code": "EMPTY", "name": "未部署", "status": "published"},
            )
            res = c.post("/v1/portal/apps/EMPTY/launch")
            self.assertFalse(res.json()["allowed"])
            self.assertEqual(res.json()["reason"], "NOT_DEPLOYED")


class TestUserFeatures(unittest.TestCase):
    def test_favorite_add_list_duplicate_remove(self) -> None:
        with api_client() as c:
            aid = get_app_id_by_code("PUB")
            h = user_headers()
            self.assertEqual(c.post(f"/v1/portal/me/favorites/{aid}", headers=h).status_code, 200)
            self.assertEqual(len(c.get("/v1/portal/me/favorites", headers=h).json()["items"]), 1)
            self.assertEqual(c.post(f"/v1/portal/me/favorites/{aid}", headers=h).status_code, 409)
            self.assertEqual(c.delete(f"/v1/portal/me/favorites/{aid}", headers=h).status_code, 200)
            self.assertEqual(len(c.get("/v1/portal/me/favorites", headers=h).json()["items"]), 0)

    def test_user_cannot_see_others_favorites(self) -> None:
        with api_client() as c:
            aid = get_app_id_by_code("PUB")
            c.post(f"/v1/portal/me/favorites/{aid}", headers=user_headers(USER_A))
            self.assertEqual(len(c.get("/v1/portal/me/favorites", headers=user_headers(USER_B)).json()["items"]), 0)

    def test_favorite_requires_login(self) -> None:
        with api_client() as c:
            self.assertEqual(c.get("/v1/portal/me/favorites").status_code, 401)

    def test_recent_accumulates_and_limits(self) -> None:
        with api_client() as c:
            aid = get_app_id_by_code("PUB")
            h = user_headers()
            for _ in range(3):
                c.post(f"/v1/portal/me/recent/{aid}", headers=h)
            items = c.get("/v1/portal/me/recent?limit=10", headers=h).json()["items"]
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["visit_count"], 3)

    def test_body_user_id_cannot_override_identity(self) -> None:
        """尝试在 body 指定 user_sub 不改变归属——身份只来自 header。"""
        with api_client() as c:
            aid = get_app_id_by_code("PUB")
            c.post(
                f"/v1/portal/me/favorites/{aid}",
                headers=user_headers(USER_A),
                json={"user_sub": USER_B},
            )
            self.assertEqual(len(c.get("/v1/portal/me/favorites", headers=user_headers(USER_A)).json()["items"]), 1)
            self.assertEqual(len(c.get("/v1/portal/me/favorites", headers=user_headers(USER_B)).json()["items"]), 0)


class TestAdmin(unittest.TestCase):
    def test_admin_whitelist_fail_closed(self) -> None:
        with api_client(admin_config="") as c:
            self.assertEqual(c.get("/v1/portal/admin/apps", headers=admin_headers()).status_code, 403)
        with api_client() as c:
            self.assertEqual(c.get("/v1/portal/admin/apps", headers=user_headers()).status_code, 403)

    def test_create_edit_publish_disable_delete(self) -> None:
        with api_client() as c:
            h = admin_headers()
            created = c.post(
                "/v1/portal/admin/apps", headers=h,
                json={"code": "NEW1", "name": "新应用", "launch_url": "https://example.com/new"},
            )
            self.assertEqual(created.status_code, 200)
            app_id = created.json()["app"]["id"]
            self.assertEqual(created.json()["app"]["status"], "draft")
            self.assertEqual(c.get("/v1/portal/apps").json()["total"], 2)  # 草稿不公开

            edited = c.put(f"/v1/portal/admin/apps/{app_id}", headers=h, json={"subtitle": "副标题"})
            self.assertEqual(edited.json()["app"]["subtitle"], "副标题")

            published = c.post(f"/v1/portal/admin/apps/{app_id}/publish", headers=h)
            self.assertEqual(published.json()["app"]["status"], "published")
            self.assertEqual(c.get("/v1/portal/apps").json()["total"], 3)  # 发布后即刻可见

            disabled = c.post(f"/v1/portal/admin/apps/{app_id}/disable", headers=h)
            self.assertEqual(disabled.json()["app"]["status"], "disabled")
            self.assertEqual(c.get("/v1/portal/apps").json()["total"], 2)

            self.assertEqual(c.delete(f"/v1/portal/admin/apps/{app_id}", headers=h).status_code, 200)

    def test_create_published_app_sets_published_at(self) -> None:
        """PG 约束 ck_portal_apps_published 要求发布态必须有 published_at。

        创建路径必须自动补发布时间，否则本地内存库测试通过、线上 PG 报 500。
        """
        with api_client() as c:
            res = c.post(
                "/v1/portal/admin/apps", headers=admin_headers(),
                json={
                    "code": "PUBNEW", "name": "直发应用", "status": "published",
                    "launch_url": "https://example.com/pubnew",
                },
            )
            self.assertEqual(res.status_code, 200, res.text)
            app = res.json()["app"]
            self.assertEqual(app["status"], "published")
            self.assertTrue(app["published_at"], "发布态必须自动写入 published_at")

    def test_offline_soon_flag_roundtrip(self) -> None:
        """「即将下线」标识需能被管理接口写入并公开返回，默认关闭。"""
        with api_client() as c:
            res = c.post(
                "/v1/portal/admin/apps", headers=admin_headers(),
                json={
                    "code": "OFFSOON", "name": "将下线应用", "status": "published",
                    "launch_url": "https://example.com/offsoon", "is_offline_soon": True,
                },
            )
            self.assertEqual(res.status_code, 200, res.text)
            aid = res.json()["app"]["id"]
            self.assertTrue(res.json()["app"]["is_offline_soon"])

            # 公开接口也要带出该标识，供前台卡片展示提醒
            pub = c.get("/v1/portal/apps").json()["items"]
            target = next(a for a in pub if a["id"] == aid)
            self.assertTrue(target["is_offline_soon"])

            # 更新接口可关闭；布尔类型必须校验
            upd = c.put(
                f"/v1/portal/admin/apps/{aid}", headers=admin_headers(),
                json={"is_offline_soon": False},
            )
            self.assertEqual(upd.status_code, 200, upd.text)
            self.assertFalse(upd.json()["app"]["is_offline_soon"])
            bad = c.put(
                f"/v1/portal/admin/apps/{aid}", headers=admin_headers(),
                json={"is_offline_soon": "yes"},
            )
            self.assertEqual(bad.status_code, 422)

    def test_dangerous_launch_url_rejected(self) -> None:
        for bad in ("javascript:alert(1)", "data:text/html,x", "//evil.com/x", "https://u:p@example.com"):
            with self.subTest(bad=bad):
                with api_client() as c:
                    res = c.post(
                        "/v1/portal/admin/apps", headers=admin_headers(),
                        json={"code": "BAD", "name": "危险地址", "launch_url": bad},
                    )
                    self.assertEqual(res.status_code, 422)

    def test_homepage_recommendation_takes_effect_immediately(self) -> None:
        with api_client() as c:
            h = admin_headers()
            aid = get_app_id_by_code("DRAFT")
            res = c.put(
                "/v1/portal/admin/homepage", headers=h,
                json={"items": [{"id": aid, "show_on_home": True, "is_featured": True, "sort_order": 1}]},
            )
            self.assertEqual(res.status_code, 200)
            # 草稿即使标记推荐也不公开；先发布再验证
            c.post(f"/v1/portal/admin/apps/{aid}/publish", headers=h)
            self.assertEqual(c.get("/v1/portal/apps/featured").json()["total"], 1)
            self.assertEqual(c.get("/v1/portal/apps?home=true").json()["total"], 1)

    def test_category_crud_and_delete_detaches(self) -> None:
        with api_client() as c:
            h = admin_headers()
            created = c.post(
                "/v1/portal/admin/categories", headers=h,
                json={"code": "newcat", "name": "新分类", "sort_order": 99},
            )
            self.assertEqual(created.status_code, 200)
            cid = created.json()["category"]["id"]
            self.assertEqual(c.put(f"/v1/portal/admin/categories/{cid}", headers=h, json={"name": "改名"}).json()["category"]["name"], "改名")
            self.assertEqual(c.delete(f"/v1/portal/admin/categories/{cid}", headers=h).status_code, 200)
            self.assertEqual(c.get("/v1/portal/admin/categories", headers=h).json()["total"], 2)

    def test_delete_app_cascades_favorites_and_visits(self) -> None:
        with api_client() as c:
            h = admin_headers()
            created = c.post(
                "/v1/portal/admin/apps", headers=h,
                json={"code": "CASCADE", "name": "级联", "status": "published",
                      "launch_url": "https://x.example"},
            )
            aid = created.json()["app"]["id"]
            c.post(f"/v1/portal/me/favorites/{aid}", headers=user_headers())
            c.post(f"/v1/portal/me/recent/{aid}", headers=user_headers())
            self.assertEqual(len(c.get("/v1/portal/me/favorites", headers=user_headers()).json()["items"]), 1)
            self.assertEqual(c.delete(f"/v1/portal/admin/apps/{aid}", headers=h).status_code, 200)
            self.assertEqual(len(c.get("/v1/portal/me/favorites", headers=user_headers()).json()["items"]), 0)
            self.assertEqual(len(c.get("/v1/portal/me/recent", headers=user_headers()).json()["items"]), 0)


class TestMyCapabilities(unittest.TestCase):
    def test_capabilities_follow_admin_whitelist(self) -> None:
        """前端据此决定显示后台入口：匿名/普通用户false，白名单用户true，空白名单fail-closed。"""
        with api_client() as c:
            anon = c.get("/v1/portal/me/capabilities")
            self.assertEqual(anon.status_code, 200)
            self.assertEqual(anon.json(), {
                "authenticated": False, "is_admin": False, "can_manage_apps": False,
            })

            user = c.get("/v1/portal/me/capabilities", headers=user_headers()).json()
            self.assertEqual(user, {
                "authenticated": True, "is_admin": False, "can_manage_apps": False,
            })

            admin = c.get("/v1/portal/me/capabilities", headers=admin_headers()).json()
            self.assertEqual(admin, {
                "authenticated": True, "is_admin": True, "can_manage_apps": True,
            })

        # 白名单为空时即便头部声称是管理员也必须 false（与管理接口 fail-closed 一致）
        with api_client(admin_config="") as c:
            fail_closed = c.get("/v1/portal/me/capabilities", headers=admin_headers()).json()
            self.assertEqual(fail_closed["is_admin"], False)
            self.assertEqual(fail_closed["can_manage_apps"], False)


class TestDomainHelpers(unittest.TestCase):
    def test_uuid7_is_time_ordered_and_version_7(self) -> None:
        ids = [uuid7() for _ in range(20)]
        self.assertEqual(len(set(ids)), 20)
        self.assertTrue(all(i.version == 7 for i in ids))
        self.assertEqual(ids, sorted(ids))

    def test_validate_launch_url_accepts_empty_and_https(self) -> None:
        self.assertEqual(validate_launch_url(""), "")
        self.assertEqual(validate_launch_url("  https://a.example/app?x=1  "), "https://a.example/app?x=1")

    def test_validate_launch_url_accepts_site_relative_paths(self) -> None:
        """本站内页相对路径（单个 / 开头）合法；protocol-relative 与反斜杠拒绝。"""
        for good in ("/wedesk/", "/apps/xxx/?q=1#top", "/"):
            self.assertEqual(validate_launch_url(good), good)
        for bad in ("//evil.com/x", "/a\\b", "relative/no-slash", "/ path with space"):
            with self.assertRaises(ValidationError):
                validate_launch_url(bad)


if __name__ == "__main__":
    unittest.main()
