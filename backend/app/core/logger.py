"""全应用统一日志出口（loguru）。

约定：
    - 所有模块用 ``from ..core.logger import logger``（或相应层级）取 logger，
      不要再直接用 print() 或标准库 logging；
    - 控制台（stderr）级别由环境变量 AP_LOG_LEVEL 控制（默认 INFO）；
    - ERROR 及以上级别额外写入文件，按天轮转、保留最近 7 天，供开发排查；
      日志目录可用环境变量 AP_LOG_DIR 覆盖，默认 backend/logs/；
    - 文件日志只写运行诊断信息，不记录用户数据明文，符合零知识边界；
    - loguru 的 logger 是进程级单例，重复 import 只配置一次 sink。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger

# 纯文本格式（文件日志不带 ANSI 颜色，便于 grep / 日志采集）
_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
    "{name}:{function}:{line} - {message}"
)

_DEFAULT_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)

# backend/ 根目录：本文件位于 backend/app/core/logger.py
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_LOG_DIR = Path(os.getenv("AP_LOG_DIR", str(_BACKEND_DIR / "logs"))).expanduser()

# 幂等配置：去掉 loguru 默认 stderr sink，换成带级别/格式控制的 sink。
logger.remove()
logger.add(
    sys.stderr,
    level=os.getenv("AP_LOG_LEVEL", "INFO").upper(),
    format=_DEFAULT_FORMAT,
    backtrace=False,
    diagnose=False,
)

# ERROR+ 落盘：按天轮转，保留 7 天；目录不可写时降级为仅控制台输出。
try:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger.add(
        _LOG_DIR / "error_{time:YYYY-MM-DD}.log",
        level="ERROR",
        format=_FILE_FORMAT,
        rotation="1 day",
        retention="7 days",
        encoding="utf-8",
        backtrace=True,   # 记录异常栈的局部变量，便于排查；diagnose=False 避免泄漏敏感值
        diagnose=False,
        # 不用 enqueue：异步队列在进程退出时可能丢失最后几条 ERROR；
        # loguru 文件 sink 本身线程安全，单 worker 下同步写入更可靠。
    )
except OSError as exc:  # pragma: no cover - 仅在只读文件系统等极端环境触发
    logger.warning(f"[logger] 错误日志目录不可写（{_LOG_DIR}），仅输出到控制台：{exc}")

__all__ = ["logger"]
