"""部署配置与 passthrough 鉴权契约测试（unittest 标准库）。

覆盖云上部署引入的新行为：
  - DSN 组装：密码含 '@' 必须百分号编码，否则连库解析错乱；
  - PgBouncer(6432)：默认关闭自动 prepared statement，避免
    `prepared statement "_pg3_x" does not exist` 间歇错误；
  - CORS 白名单解析：逗号分隔、去尾斜杠、空串；
  - passthrough provider：永不 401、缺头回落默认 sub、超长 sub 拒绝；
  - /v1/auth/mode：passthrough 模式明确暴露 insecure 风险提示。
Settings 用 Settings(_env_file=None) 直测，不依赖 .env / 真实 PG / 网络。
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.auth import PassthroughProvider, UnauthorizedError, build_provider
from app.core.config import Settings
from tests.helpers import api_client, seed_app


def make_settings(**env) -> Settings:
    """直接构造隔离的 Settings（不读 .env），环境字段用 kwargs 传入。"""
    return Settings(_env_file=None, **env)


class TestDsnAssembly(unittest.TestCase):
    """分散环境变量 -> postgres:// URL 的组装（重点：凭据转义）。"""

    def test_explicit_url_takes_priority(self) -> None:
        s = make_settings(
            AP_DATABASE_URL="postgresql://a:b@c:1/d", AP_PG_HOST="ignored",
            AP_PG_USER="u", AP_PG_NAME="d",
        )
        self.assertEqual(s.database_dsn, "postgresql://a:b@c:1/d")

    def test_password_with_at_is_percent_encoded(self) -> None:
        """密码里的 @ 若裸写会被当作 host 分隔符，必须编码成 %40（用假口令测，不涉密）。"""
        s = make_settings(
            AP_PG_HOST="db.example.com", AP_PG_PORT="6432", AP_PG_NAME="tools",
            AP_PG_USER="tools", AP_PG_PASSWORD="p@ss",
        )
        url = s.database_dsn
        self.assertEqual(url, "postgresql://tools:p%40ss@db.example.com:6432/tools")
        self.assertIn("%40", url)

    def test_missing_key_parts_fail_closed_to_empty(self) -> None:
        s = make_settings(AP_PG_HOST="db.example.com")
        # 缺 user / dbname -> 返回空，交由调用方 fail-closed
        self.assertEqual(s.database_dsn, "")
        self.assertFalse(s.dsn_configured())

    def test_password_with_reserved_chars_all_encoded(self) -> None:
        s = make_settings(
            AP_PG_HOST="h", AP_PG_NAME="d", AP_PG_USER="u", AP_PG_PASSWORD="p@:/?#%",
        )
        self.assertIn("p%40%3A%2F%3F%23%25@", s.database_dsn)

    def test_sslmode_appended(self) -> None:
        s = make_settings(
            AP_PG_HOST="h", AP_PG_NAME="d", AP_PG_USER="u",
            AP_PG_PASSWORD="p", AP_PG_SSLMODE="require",
        )
        self.assertTrue(s.database_dsn.endswith("?sslmode=require"))


class TestPgBouncerKwargs(unittest.TestCase):
    def test_pgbouncer_disables_auto_prepare_by_default(self) -> None:
        s = make_settings()
        kwargs = s.pg_connect_kwargs
        self.assertIsNone(kwargs["prepare_threshold"])
        self.assertEqual(kwargs["connect_timeout"], 10)

    def test_prepare_threshold_can_be_re_enabled_explicitly(self) -> None:
        s = make_settings(AP_PG_PREPARE_THRESHOLD="5")
        self.assertEqual(s.pg_connect_kwargs["prepare_threshold"], 5)

    def test_pool_max_size_reads_env(self) -> None:
        s = make_settings(AP_PG_POOL_MAX="4")
        self.assertEqual(s.pg_pool_max_size(8), 4)


class TestPublicPath(unittest.TestCase):
    """前端公网基路径：必须与 Vite base 对齐，否则 /ap/assets/*.js 会拿到 HTML。"""

    def test_default_is_ap_subpath(self) -> None:
        s = make_settings()
        self.assertEqual(s.public_path, "/ap/")
        self.assertEqual(s.public_prefix, "ap")

    def test_normalizes_missing_slashes(self) -> None:
        s = make_settings(AP_PUBLIC_PATH="apps/mytools")
        self.assertEqual(s.public_path, "/apps/mytools/")
        self.assertEqual(s.public_prefix, "apps/mytools")

    def test_root_deployment(self) -> None:
        s = make_settings(AP_PUBLIC_PATH="/")
        self.assertEqual(s.public_path, "/")
        self.assertEqual(s.public_prefix, "")

    def test_assets_mount_paths_default_includes_base(self) -> None:
        """默认既挂 /assets 又挂 /ap/assets，去重保序。"""
        s = make_settings()
        self.assertEqual(s.assets_mount_paths, ["/assets", "/ap/assets"])

    def test_assets_mount_paths_root_only_one(self) -> None:
        s = make_settings(AP_PUBLIC_PATH="/")
        self.assertEqual(s.assets_mount_paths, ["/assets"])

    def test_assets_mount_paths_nested_base(self) -> None:
        s = make_settings(AP_PUBLIC_PATH="/apps/mytools/")
        self.assertEqual(s.assets_mount_paths, ["/assets", "/apps/mytools/assets"])


class TestCorsOrigins(unittest.TestCase):
    def test_parse_comma_separated_and_strip_slash(self) -> None:
        s = make_settings(AP_CORS_ORIGINS="https://alice.github.io/, https://tools.example.com ,")
        self.assertEqual(
            s.cors_origin_list,
            ["https://alice.github.io", "https://tools.example.com"],
        )

    def test_empty_means_same_origin_only(self) -> None:
        s = make_settings(AP_CORS_ORIGINS="")
        self.assertEqual(s.cors_origin_list, [])

    def test_admin_subs_and_tool_ids_parse(self) -> None:
        s = make_settings(PORTAL_ADMIN_SUBS=" a , b ,", AP_TOOL_IDS="safekeep,notes")
        self.assertEqual(s.portal_admin_sub_set, {"a", "b"})
        self.assertEqual(s.allowed_tool_id_set, {"safekeep", "notes"})


class TestPassthroughProvider(unittest.TestCase):
    def test_reads_declared_sub(self) -> None:
        p = PassthroughProvider()
        self.assertEqual(p.authenticate(headers={"x-user-sub": "logto|abc"}).sub, "logto|abc")

    def test_missing_header_falls_back_never_401(self) -> None:
        """与 dev 模式的关键差别：passthrough 缺头不拒绝，回落默认 sub。"""
        p = PassthroughProvider(default_sub="anon")
        self.assertEqual(p.authenticate(headers={}).sub, "anon")

    def test_custom_default_sub(self) -> None:
        p = PassthroughProvider(header="X-User", default_sub="guest")
        self.assertEqual(p.authenticate(headers={}).sub, "guest")
        self.assertEqual(p.authenticate(headers={"x-user": "bob"}).sub, "bob")

    def test_oversized_sub_rejected(self) -> None:
        with self.assertRaises(UnauthorizedError):
            PassthroughProvider().authenticate(headers={"x-user-sub": "x" * 300})

    def test_factory_wires_passthrough(self) -> None:
        p = build_provider(mode="passthrough", passthrough_default_sub="anon")
        self.assertIsInstance(p, PassthroughProvider)
        self.assertEqual(p.mode, "passthrough")


class TestPassthroughAPIMode(unittest.TestCase):
    """passthrough 身份装配时：/v1/auth/mode 暴露 insecure 提示；无头写入落默认槽。"""

    def test_mode_reports_insecure(self) -> None:
        with api_client(seed_fixtures=False, auth_provider=PassthroughProvider()) as client:
            seed_app(code="SAFEKEEP", name="锦囊", status="published")
            body = client.get("/v1/auth/mode").json()
            self.assertEqual(body["mode"], "passthrough")
            self.assertFalse(body["secure"])
            self.assertIn("不鉴权", body["warning"])

    def test_passthrough_writes_without_header_land_in_default_slot(self) -> None:
        with api_client(seed_fixtures=False, auth_provider=PassthroughProvider()) as client:
            seed_app(code="SAFEKEEP", name="锦囊", status="published")
            # 无身份头：不 401，写入匿名槽
            r = client.put(
                "/v1/configs/safekeep/vault",
                json={"value": {"ct": "x"}, "expected_revision": 0},
            )
            self.assertEqual(r.status_code, 200)
            self.assertEqual(
                client.get("/v1/configs/safekeep/vault").status_code, 200)
            # 换成声明身份头：同一 key 在匿名槽仍在，alice 槽新写
            r2 = client.put(
                "/v1/configs/safekeep/vault",
                json={"value": {"ct": "y"}, "expected_revision": 0},
                headers={"X-User-Sub": "logto|alice"},
            )
            self.assertEqual(r2.status_code, 200)
            anon = client.get("/v1/configs/safekeep/vault")
            self.assertEqual(anon.json()["value"], {"ct": "x"})
            alice = client.get("/v1/configs/safekeep/vault",
                               headers={"X-User-Sub": "logto|alice"})
            self.assertEqual(alice.json()["value"], {"ct": "y"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
