"""公共配置表 + 鉴权 + API 契约测试（unittest 标准库 + FastAPI TestClient）。

覆盖：
  - 存储层：CAS 乐观锁、软删除、多租户/多工具隔离、零知识（value 原样存取且不解析）。
  - 鉴权层：user_sub 唯一来自 provider；dev 头缺失拒绝；stub 固定身份；Logto fail-closed。
  - API 层：响应 schema 稳定、ETag、配额、错误码统一、越权不可指定他人身份、
            /v1/auth/mode 风险提示、旧元信息接口回归。
测试不依赖真实 PG、真实 JWT 租户或真实时钟：数据层走 SQLite 内存引擎
（与生产共用同一套 SQLModel/DAL/Service 代码路径）。
"""

from __future__ import annotations

import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.auth import DevHeaderProvider, LogtoJWTProvider, StubProvider, UnauthorizedError
from tests.helpers import api_client, patch_env, seed_app

# 一个典型的「零知识密文 blob」：只有 iv/ct/salt 等密封字段，没有明文
CIPHER_BLOB = {
    "account": {
        "v": 1,
        "app": "safekeep-local",
        "salt": "c2FsdA==",
        "kdf": {"alg": "PBKDF2-SHA256", "iterations": 600000},
        "wrapped": {"iv": "aXY=", "ct": "Y3Q="},
        "recovery": {"salt": "cnNhbHQ=", "iv": "cml2", "ct": "cmN0"},
    },
    "items": {"id-1": {"id": "id-1", "rev": 1, "iv": "AA==", "ct": "BB==", "deleted": False}},
    "rev": 1,
}


def _with_safekeep(auth_provider):
    """标准配置测试环境：stub 身份 + 已发布的 SAFEKEEP 应用（工具准入权威）。"""
    return api_client(
        seed_fixtures=False,
        auth_provider=auth_provider,
    )


def _seed_safekeep(**extra) -> None:
    seed_app(
        code="SAFEKEEP", name="锦囊", status="published", visibility="public",
        **extra,
    )


class TestAuthProviders(unittest.TestCase):
    def test_dev_header_provider_reads_sub_and_rejects_missing(self) -> None:
        p = DevHeaderProvider()
        self.assertEqual(p.authenticate(headers={"x-user-sub": "alice"}).sub, "alice")
        with self.assertRaises(UnauthorizedError):
            p.authenticate(headers={})

    def test_stub_provider_fixed_identity(self) -> None:
        p = StubProvider("fixed")
        self.assertEqual(p.authenticate(headers={}).sub, "fixed")

    def test_logto_not_configured_fails_closed(self) -> None:
        p = LogtoJWTProvider(issuer="", audience="", jwks_url="")
        self.assertFalse(p.configured)
        with self.assertRaises(UnauthorizedError) as ctx:
            p.authenticate(headers={"authorization": "Bearer whatever"})
        self.assertEqual(ctx.exception.code, "AUTH_NOT_CONFIGURED")

    def test_logto_rejects_non_bearer(self) -> None:
        p = LogtoJWTProvider(issuer="https://x/oidc", audience="api", jwks_url="https://x/jwks")
        with self.assertRaises(UnauthorizedError):
            p.authenticate(headers={"authorization": "Basic abc"})


class TestConfigAPI(unittest.TestCase):
    """配置 API 契约：身份固定 stub "test-user"。"""

    def setUp(self) -> None:
        self._cm = _with_safekeep(StubProvider("test-user"))
        self.client = self._cm.__enter__()
        _seed_safekeep()

    def tearDown(self) -> None:
        self._cm.__exit__(None, None, None)

    def test_list_empty(self) -> None:
        r = self.client.get("/v1/configs/safekeep")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["tool_id"], "safekeep")
        self.assertEqual(body["count"], 0)
        self.assertEqual(body["items"], [])

    def test_put_then_get_with_etag(self) -> None:
        r = self.client.put(
            "/v1/configs/safekeep/vault",
            json={"value": CIPHER_BLOB, "expected_revision": 0},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("etag"), 'W/"1"')
        body = r.json()
        self.assertEqual(body["revision"], 1)
        self.assertEqual(body["value"], CIPHER_BLOB)  # 零知识：原样回显密文
        self.assertNotIn("user_sub", body)  # 归属用户不下发、不由客户端指定

        g = self.client.get("/v1/configs/safekeep/vault")
        self.assertEqual(g.status_code, 200)
        self.assertEqual(g.json()["value"], CIPHER_BLOB)

    def test_update_requires_correct_revision(self) -> None:
        self.client.put("/v1/configs/safekeep/k", json={"value": {"v": 1}, "expected_revision": 0})
        ok = self.client.put("/v1/configs/safekeep/k", json={"value": {"v": 2}, "expected_revision": 1})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["revision"], 2)
        conflict = self.client.put(
            "/v1/configs/safekeep/k", json={"value": {"v": 3}, "expected_revision": 1}
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["error"], "REVISION_CONFLICT")
        self.assertEqual(conflict.json()["detail"]["actual"], 2)

    def test_first_create_rejects_overwrite(self) -> None:
        self.client.put("/v1/configs/safekeep/k", json={"value": {"a": 1}, "expected_revision": 0})
        again = self.client.put("/v1/configs/safekeep/k", json={"value": {"a": 2}, "expected_revision": 0})
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["error"], "REVISION_CONFLICT")
        self.assertEqual(again.json()["detail"]["actual"], 1)

    def test_delete_soft_and_requires_revision(self) -> None:
        self.client.put("/v1/configs/safekeep/k", json={"value": {"v": 1}, "expected_revision": 0})
        missing_rev = self.client.delete("/v1/configs/safekeep/k")
        self.assertEqual(missing_rev.status_code, 422)  # expected_revision 必填
        d = self.client.delete("/v1/configs/safekeep/k?expected_revision=1")
        self.assertEqual(d.status_code, 200)
        self.assertIsNotNone(d.json()["deleted_at"])
        self.assertEqual(self.client.get("/v1/configs/safekeep/k").status_code, 404)
        rows = self.client.get("/v1/configs/safekeep?include_deleted=true").json()["items"]
        self.assertEqual(len(rows), 1)

    def test_cross_user_isolation_via_api(self) -> None:
        self.client.put("/v1/configs/safekeep/k", json={"value": {"secret": "x"}, "expected_revision": 0})
        # 切到另一个 stub 身份
        self.client.app.state.auth_provider = StubProvider("another-user")
        self.assertEqual(self.client.get("/v1/configs/safekeep").json()["count"], 0)
        self.assertEqual(self.client.get("/v1/configs/safekeep/k").status_code, 404)

    def test_cannot_choose_own_identity_from_body_or_query(self) -> None:
        """越权防线：body/query 里的 user_id 一律被忽略，归属只由 provider 决定。"""
        self.client.put(
            "/v1/configs/safekeep/k?user_id=victim",
            json={"value": {"v": 1}, "expected_revision": 0, "user_id": "victim", "user_sub": "victim"},
        )
        g = self.client.get("/v1/configs/safekeep/k")
        self.assertEqual(g.status_code, 200)
        # victim 身份下取不到
        self.client.app.state.auth_provider = StubProvider("victim")
        self.assertEqual(self.client.get("/v1/configs/safekeep/k").status_code, 404)

    def test_invalid_ids_and_value_size(self) -> None:
        self.assertEqual(self.client.put("/v1/configs/BAD!/k", json={"value": 1, "expected_revision": 0}).status_code, 400)
        self.assertEqual(self.client.put("/v1/configs/safekeep/_quota", json={"value": 1, "expected_revision": 0}).status_code, 400)
        huge = "x" * (600 * 1024)
        r = self.client.put("/v1/configs/safekeep/k", json={"value": huge, "expected_revision": 0})
        self.assertEqual(r.status_code, 413)
        self.assertEqual(r.json()["error"], "VALUE_TOO_LARGE")

    def test_quota_endpoint(self) -> None:
        r = self.client.get("/v1/configs/safekeep/_quota")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["max_keys"], 200)
        self.assertEqual(r.json()["max_value_bytes"], 524288)

    def test_unknown_tool_404_when_whitelist_set(self) -> None:
        """环境变量白名单是注册表之上的第二道门：注册表中存在但白名单排除 → 404。"""
        with patch_env(AP_TOOL_IDS="safekeep"):
            r = self.client.get("/v1/configs/ghosttool")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["error"], "TOOL_NOT_FOUND")

    def test_missing_dev_header_returns_401_when_dev_mode(self) -> None:
        self.client.app.state.auth_provider = DevHeaderProvider()
        r = self.client.get("/v1/configs/safekeep")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["error"], "UNAUTHORIZED")
        ok = self.client.get("/v1/configs/safekeep", headers={"X-User-Sub": "bob"})
        self.assertEqual(ok.status_code, 200)

    def test_new_fields_roundtrip_and_device_is_metadata_not_value(self) -> None:
        """schema_version/device 随 API 往返；device 不混入 value（零知识内容不变）。"""
        r = self.client.put(
            "/v1/configs/safekeep/vault",
            json={
                "value": CIPHER_BLOB, "expected_revision": 0,
                "schema_version": 9, "updated_by_device": "chrome-win",
            },
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["schema_version"], 9)
        self.assertEqual(body["updated_by_device"], "chrome-win")
        self.assertEqual(body["value"], CIPHER_BLOB)  # value 原样，device 未渗入
        g = self.client.get("/v1/configs/safekeep/vault").json()
        self.assertEqual((g["schema_version"], g["updated_by_device"]), (9, "chrome-win"))
        self.assertEqual(g["revision"], 1)  # revision 独立，仍是 1

    def test_new_fields_defaults(self) -> None:
        r = self.client.put(
            "/v1/configs/safekeep/k", json={"value": {"a": 1}, "expected_revision": 0}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["schema_version"], 1)
        self.assertIsNone(r.json()["updated_by_device"])

    def test_invalid_schema_version_and_long_device_rejected(self) -> None:
        self.assertEqual(
            self.client.put(
                "/v1/configs/safekeep/k",
                json={"value": 1, "expected_revision": 0, "schema_version": 0},
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.put(
                "/v1/configs/safekeep/k",
                json={"value": 1, "expected_revision": 0, "updated_by_device": "d" * 200},
            ).status_code,
            422,
        )

    def test_registry_gate_blocks_unregistered_and_disabled_tools(self) -> None:
        """注册表是工具准入权威：未注册 / 已停用（draft）→ 404。"""
        self.assertEqual(self.client.get("/v1/configs/ghosttool").status_code, 404)
        seed_app(code="RETIRED", name="退役", status="draft")
        self.assertEqual(self.client.get("/v1/configs/retired").status_code, 404)
        self.assertEqual(
            self.client.put(
                "/v1/configs/retired/k", json={"value": 1, "expected_revision": 0}
            ).status_code,
            404,
        )

    def test_quota_exceeded_enforced(self) -> None:
        """AP_MAX_KEYS 配额：超出后新建返回 409 QUOTA_EXCEEDED。"""
        with patch_env(AP_MAX_KEYS="2"):
            self.client.put("/v1/configs/safekeep/k1", json={"value": {"x": 1}, "expected_revision": 0})
            self.client.put("/v1/configs/safekeep/k2", json={"value": {"x": 1}, "expected_revision": 0})
            r = self.client.put("/v1/configs/safekeep/k3", json={"value": {"x": 1}, "expected_revision": 0})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["error"], "QUOTA_EXCEEDED")


class TestToolsAPI(unittest.TestCase):
    """/v1/tools：以 portal_apps 为权威（published ≙ enabled）。"""

    def setUp(self) -> None:
        self._cm = _with_safekeep(StubProvider("test-user"))
        self.client = self._cm.__enter__()
        _seed_safekeep()
        seed_app(code="ALSO_TOOLS", name="Also Tools", status="draft")

    def tearDown(self) -> None:
        self._cm.__exit__(None, None, None)

    def test_list_tools_returns_published_only(self) -> None:
        r = self.client.get("/v1/tools")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["items"][0]["tool_id"], "safekeep")
        self.assertTrue(body["items"][0]["enabled"])

    def test_get_tool_and_hidden_when_disabled(self) -> None:
        r = self.client.get("/v1/tools/safekeep")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["name"], "锦囊")
        self.assertEqual(self.client.get("/v1/tools/also_tools").status_code, 404)  # draft 不准入
        self.assertEqual(self.client.get("/v1/tools/gone").status_code, 404)

    def test_tools_requires_auth(self) -> None:
        self.client.app.state.auth_provider = DevHeaderProvider()
        self.assertEqual(self.client.get("/v1/tools").status_code, 401)
        self.assertEqual(
            self.client.get("/v1/tools", headers={"X-User-Sub": "bob"}).status_code, 200
        )

    def test_tools_carry_no_user_data(self) -> None:
        """工具清单是全局元数据：字段形状固定，不含 user_sub / value / 密文字段。"""
        item = self.client.get("/v1/tools").json()["items"][0]
        self.assertEqual(
            set(item.keys()),
            {
                "tool_id", "name", "icon", "description", "enabled", "sort_order",
                "default_max_keys", "default_max_value_bytes", "created_at", "updated_at",
            },
        )


class TestAuthModeAndRegression(unittest.TestCase):
    def setUp(self) -> None:
        self._cm = _with_safekeep(StubProvider("test-user"))
        self.client = self._cm.__enter__()

    def tearDown(self) -> None:
        self._cm.__exit__(None, None, None)

    def test_auth_mode_exposes_risk(self) -> None:
        r = self.client.get("/v1/auth/mode")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["mode"], "stub")
        self.assertFalse(body["secure"])
        self.assertIsNotNone(body["warning"])

    def test_auth_mode_secure_when_logto_configured(self) -> None:
        self.client.app.state.auth_provider = LogtoJWTProvider(
            issuer="https://x/oidc", audience="api", jwks_url="https://x/jwks")
        body = self.client.get("/v1/auth/mode").json()
        self.assertEqual(body["mode"], "logto")
        self.assertTrue(body["secure"])
        self.assertTrue(body["logto_configured"])

    def test_meta_endpoints_still_work(self) -> None:
        self.assertEqual(self.client.get("/v1/health").status_code, 200)
        v = self.client.get("/v1/version").json()
        self.assertTrue(v["zero_knowledge"])
        self.assertEqual(self.client.get("/v1/definitely-not-a-route").json()["error"], "NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
