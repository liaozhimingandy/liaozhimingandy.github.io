"""架构解耦守卫测试：workflow 核心不得依赖 FastAPI。

固化分层约束（对应重构验收标准「工作流核心模块不依赖 FastAPI」）：
    1. 子进程模拟「未安装 FastAPI」环境，import 工作流核心必须成功；
    2. 源码扫描：workflow 核心文件与 standalone 入口不得出现 Web 层导入；
    3. GraphService.run 便捷接口委托 runner.run_one（同一套执行逻辑）。

这类测试防止未来有人把 router/Depends 又塞回 workflow 包——
一旦违反，CI 直接红。
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parents[1]

# workflow 核心：允许 import 的只有 langgraph/langchain/httpx/loguru/
# pydantic-settings/sqlmodel 等非 Web 依赖
WORKFLOW_CORE_FILES = [
    "app/article/__init__.py",
    "app/article/graph/__init__.py",
    "app/article/graph/config.py",
    "app/article/graph/state.py",
    "app/article/graph/nodes.py",
    "app/article/graph/saver.py",
    "app/article/graph/builder.py",
    "app/article/graph/runner.py",
    "app/article/graph/service.py",
    "app/article/worker.py",
    "standalone/run_workflow.py",
]

_FORBIDDEN_SNIPPETS = ("from fastapi", "import fastapi", "Depends", "HTTPException",
                       "from starlette", "import starlette")


class TestNoFastAPIInWorkflowCore(unittest.TestCase):
    """源码级守卫：workflow 核心与独立入口不得引用 Web 层。"""

    def test_core_files_have_no_web_imports(self) -> None:
        for rel in WORKFLOW_CORE_FILES:
            src = (BACKEND_DIR / rel).read_text(encoding="utf-8")
            for snippet in _FORBIDDEN_SNIPPETS:
                self.assertNotIn(
                    snippet, src,
                    f"{rel} 出现 Web 层依赖 {snippet!r}——workflow 不得依赖 FastAPI")

    def test_import_workflow_without_fastapi_installed(self) -> None:
        """子进程屏蔽 fastapi/starlette 后 import 工作流核心必须成功。

        sys.modules 里塞 None 会让后续 import fastapi 直接 ImportError，
        等价于「环境里没装 FastAPI」。
        """
        code = (
            "import sys\n"
            "sys.modules['fastapi'] = None\n"
            "sys.modules['starlette'] = None\n"
            "sys.modules['fastapi.testclient'] = None\n"
            "import app.article.graph.service as gs\n"
            "import app.article.graph.builder as gb\n"
            "import app.article.graph.runner as gr\n"
            "assert callable(gb.get_graph) and callable(gs.get_graph_service)\n"
            "print('STANDALONE_IMPORT_OK')\n"
        )
        proc = subprocess.run([sys.executable, "-c", code], cwd=BACKEND_DIR,
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0,
                         f"无 FastAPI 环境导入工作流失败：\n{proc.stderr[-2000:]}")
        self.assertIn("STANDALONE_IMPORT_OK", proc.stdout)

    def test_standalone_script_help_runs_without_fastapi(self) -> None:
        """standalone 入口 --help 可独立运行（argparse，不触 DB/LLM）。

        是否真不依赖 FastAPI 由上面两个测试保证（源码扫描 + 屏蔽导入）；
        本测试只验证脚本能独立启动。
        """
        import os

        proc = subprocess.run([sys.executable, "standalone/run_workflow.py", "--help"],
                              cwd=BACKEND_DIR, capture_output=True, text=True,
                              timeout=120, env=dict(os.environ))
        self.assertEqual(proc.returncode, 0, proc.stderr[-1000:])
        self.assertIn("--event-id", proc.stdout)


class TestGraphServiceRun(unittest.IsolatedAsyncioTestCase):
    """统一调用接口：run 便捷入口与分段接口共用同一执行逻辑。"""

    async def test_run_delegates_to_runner(self) -> None:
        from app.article.graph.service import GraphService

        svc = GraphService()
        material = {"id": 1, "event_title": "标题", "source_contents": ["正文"]}
        with mock.patch("app.article.graph.runner.run_one",
                        return_value={"final_article": "定稿"}) as p:
            state = svc.run(material, "t-run", auto_approve=True)
        self.assertEqual(state["final_article"], "定稿")
        p.assert_called_once_with(material, "t-run", auto_approve=True)


if __name__ == "__main__":
    unittest.main()
