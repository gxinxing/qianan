"""腾讯云函数 SCF 主入口文件。

部署配置
---------
函数名称: qianan-api
运行时:    Python 3.10
处理器:    scf_entry.main_handler
触发方式:  HTTP 触发器 / API 网关
超时:      120 秒（真实 AI 生成需要 20-30s）
内存:      512 MB

环境变量（在 SCF 控制台配置）
------------------------------
BAILIAN_API_KEY  = 百炼平台 API Key（黑客松发放）
QIANAN_MOCK      = 1（无 key 时自动 mock）/ 0（真实模式）
BAILIAN_BASE_URL = 百炼网关地址
BAILIAN_BASE_URL = ${env:BAILIAN_BASE_URL}

部署步骤见 SCF_DEPLOY.md
"""
from __future__ import annotations

import logging

from scf_adapter import scf_handler

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def main_handler(event: dict, context: Any) -> dict:
    """SCF Python 3.10 HTTP 触发器入口。

    Parameters
    ----------
    event : dict
        SCF 透传的 HTTP 事件（含 requestContext / headers / body / queryString）
    context : dict
        SCF 函数上下文（含 requestId / functionName / memoryLimitInMB 等）

    Returns
    -------
    dict
        {"statusCode": int, "headers": dict, "body": str}
    """
    request_id = getattr(context, "request_id", context.get("request_id", "?"))
    logger.info("SCF invoke: request_id=%s, path=%s", request_id,
                event.get("requestContext", {}).get("path", "?"))

    try:
        return scf_handler(event, context)
    except Exception as exc:
        logger.exception("SCF handler failed: %s", exc)
        return {
            "statusCode": 500,
            "headers": {"content-type": "application/json"},
            "body": '{"detail": "Internal Server Error"}',
        }
