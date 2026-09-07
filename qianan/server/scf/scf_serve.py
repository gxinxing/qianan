"""SCF Web 函数（Type=HTTP）启动入口：uvicorn 直服 FastAPI 于 0.0.0.0:9000。

CloudBase 网关将 /api/** 以原始 HTTP 转发到本端口；本脚本由 scf_bootstrap
（/var/lang/python310/bin/python3.10 -u scf_serve.py）拉起。

loop 固定 asyncio：vendored uvloop 的 .so 在平台上的加载行为未验证，
演示期优先稳态（uvloop 仅性能优化，非功能依赖）。
"""
from __future__ import annotations

import os

import uvicorn

from app.main import app

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "9000")),
        log_level="warning",
        access_log=False,
        loop="asyncio",
        ws="none",
    )
