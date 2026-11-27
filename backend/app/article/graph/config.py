"""文章生成工作流配置区：LLM 连接参数与 HTTP 客户端。

从原 app/article/llm.py「配置区」原样迁移（逻辑零改动）：
LLM 连接参数统一来自 core.config.Settings（.env 自动加载 / 环境变量优先，
密钥不入码）；模块级常量名保留，供 service 等既有调用点使用。
"""

from ...core.logger import logger

from ...core.config import get_settings

# LLM 连接参数（环境变量：LLM_BASE_URL / LLM_API_KEY / LLM_MODEL / LLM_RETRIES）
_settings = get_settings()
LLM_BASE_URL = _settings.LLM_BASE_URL
LLM_API_KEY = _settings.LLM_API_KEY
LLM_MODEL = _settings.LLM_MODEL
LLM_RETRIES = max(0, int(_settings.LLM_RETRIES))

if not LLM_API_KEY:
    logger.warning("[llm] ⚠️ 未设置 LLM_API_KEY（.env 或环境变量），调用将无法通过鉴权")

# verify=False：走本地代理时证书链会变；如需强校验改为 True
import httpx

unsafe_http_client = httpx.Client(
    verify=False,
    timeout=httpx.Timeout(
        connect=30.0,
        read=None,       # 不限制等待响应数据的时间
        write=60.0,
        pool=30.0,
    ),
)
