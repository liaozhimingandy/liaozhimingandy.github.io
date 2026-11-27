"""提示词统一加载器。

所有提示词放在项目根的 prompt/ 目录，按功能分子目录，
每个功能固定两个文件（可只放其一）：

    prompt/
    ├── outline/          生成大纲
    │   ├── system.md     角色设定与硬性约束
    │   └── user.md       任务输入与输出格式（含 {占位符}）
    ├── outline_revise/   按人工意见修订大纲
    ├── draft/            生成母稿
    ├── multi_platform/   多平台改编
    └── check/            自动质检

调用方：llm.py 通过 get_prompt(func, role) 取原文并 .format(**state) 填充占位符。
修改提示词只需编辑 md 文件，无需改代码；带缓存，同一进程只读盘一次。
"""

from ..core.logger import logger

from pathlib import Path

# 项目根的 prompt 目录
PROMPT_DIR = Path(__file__).resolve().parent / "prompt"

_CACHE = {}  # (func, role) -> 提示词文本

VALID_ROLES = ("system", "user")


def get_prompt(func: str, role: str = "user") -> str:
    """读取某功能的提示词原文。

    func: 功能名，即 prompt/ 下的子目录名（如 "draft"）
    role: "system" 或 "user"
    文件缺失返回空串；内容首尾空白会去掉。
    """
    role = role if role in VALID_ROLES else "user"
    key = (func, role)
    if key not in _CACHE:
        path = PROMPT_DIR / func / f"{role}.md"
        try:
            _CACHE[key] = path.read_text(encoding="utf-8").strip()
        except OSError:
            logger.info(f"[prompt] 提示词文件缺失：{path}")
            _CACHE[key] = ""
    return _CACHE[key]


def reload_prompt(func: str = None, role: str = None):
    """手动清除缓存重新读盘，方便热更新调试。

    func/role 都给则只清一项；都不给则全清。
    """
    if func is None:
        _CACHE.clear()
        return
    roles = (role,) if role in VALID_ROLES else VALID_ROLES
    for r in roles:
        _CACHE.pop((func, r), None)


def list_prompts() -> dict:
    """盘点现有提示词：{"outline": ["system", "user"], ...}，便于检查完整性。"""
    out = {}
    if not PROMPT_DIR.is_dir():
        return out
    for sub in sorted(PROMPT_DIR.iterdir()):
        if not sub.is_dir():
            continue
        roles = [r for r in VALID_ROLES if (sub / f"{r}.md").is_file()]
        if roles:
            out[sub.name] = roles
    return out


if __name__ == "__main__":
    logger.info(f"[prompt] 目录：{PROMPT_DIR}")
    inventory = list_prompts()
    if not inventory:
        logger.info("[prompt] 未发现任何提示词")
    for name, roles in inventory.items():
        for r in roles:
            text = get_prompt(name, r)
            logger.info(f"  {name}/{r}.md  {len(text)} 字符")
