"""腾讯云函数 (SCF) HTTP 触发器适配器。

架构
-----
1. 首调用时在 daemon thread 中启动 uvicorn ASGI server
2. 主线程通过 httpx 向 server 发送 HTTP 请求
3. SCF 函数返回后 daemon thread 自动销毁

特性
-----
* 自动冷启动：首次请求自动拉起 uvicorn（~1.5s 开销）
* 惰性复用：同一 SCF 实例内后续请求复用 server
* 线程安全：start_server() 用锁保护，仅启动一次
* 超时保护：转发请求带 90s 超时（云函数上限 120s，留 30s buffer）
* 路径翻译：SCF event → HTTP 请求 → FastAPI 路由

部署步骤见 SCF_DEPLOY.md
"""
from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from typing import Any


# ─────────────────── 全局状态 ───────────────────

_SERVER_THREAD: threading.Thread | None = None
_SERVER_LOCK = threading.Lock()
_SERVER_READY = threading.Event()
_SERVER_URL = "http://127.0.0.1:9000"
_START_TIMEOUT = 8.0  # 冷启动等待上限（秒）


# ─────────────────── ASGI Server ───────────────────

def _start_asgi_server() -> None:
    """在 daemon thread 中启动 uvicorn ASGI server。线程安全，仅启动一次。"""
    global _SERVER_THREAD

    with _SERVER_LOCK:
        if _SERVER_THREAD is not None and _SERVER_THREAD.is_alive():
            return  # 已在运行

        _SERVER_READY.clear()

        def _run() -> None:
            import uvicorn
            from app.main import app as _app
            config = uvicorn.Config(
                _app,
                host="127.0.0.1",
                port=9000,
                log_level="warning",
                access_log=False,
            )
            server = uvicorn.Server(config)
            asyncio.run(server.serve())

        _SERVER_THREAD = threading.Thread(target=_run, daemon=True)
        _SERVER_THREAD.start()

    # 等待 server 就绪（probe / 超时）
    deadline = time.monotonic() + _START_TIMEOUT
    import urllib.request
    while time.monotonic() < deadline:
        try:
            r = urllib.request.urlopen(f"{_SERVER_URL}/api/health", timeout=1)
            if r.status == 200:
                _SERVER_READY.set()
                return
        except Exception:
            pass
        time.sleep(0.3)

    # 超时：记录警告但不阻塞（SCF 可能会有重试）
    import logging
    logging.getLogger(__name__).warning(
        "SCF ASGI server 冷启动超时 %ds，首次请求可能失败", _START_TIMEOUT
    )


# ─────────────────── ASGI → SCF 响应 ───────────────────

def _asgi_scope_to_request(method: str, path: str, query: str,
                           headers: dict, body: bytes) -> dict:
    """将 SCF HTTP 信息构造成 ASGI scope dict。"""
    scope_headers = []
    for k, v in headers.items():
        scope_headers.append([k.lower().encode(), v.encode()])

    return {
        "type": "http",
        "method": method.upper(),
        "path": path.split("?")[0],
        "query_string": query.encode(),
        "headers": scope_headers,
        "http_version": "1.1",
        "scheme": "https",
        "server": ("127.0.0.1", 9000),
        "root_path": "",
        "body": body,
    }


async def _call_asgi(scope: dict, body: bytes) -> tuple[int, dict, bytes]:
    """直接调用 FastAPI ASGI app，返回 (status, headers, body)。"""
    from app.main import app as _app

    received = False
    status_code = 500
    response_headers: list[tuple[bytes, bytes]] = []
    response_body = bytearray()

    async def receive() -> dict:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict) -> None:
        nonlocal received, status_code, response_headers, response_body
        if message["type"] == "http.response.start":
            status_code = message["status"]
            response_headers = [
                (k.decode() if isinstance(k, bytes) else k,
                 v.decode() if isinstance(v, bytes) else v)
                for k, v in message.get("headers", [])
            ]
            received = True
        elif message["type"] == "http.response.body":
            response_body.extend(message.get("body", b""))

    await _app(scope, receive, send)
    assert received, "ASGI app 未发送 response.start — 可能是 lifespan 异常"
    headers_dict = {k: v for k, v in response_headers}
    return status_code, headers_dict, bytes(response_body)


def _call_asgi_sync(method: str, path: str, query: str,
                    headers: dict, body: bytes,
                    timeout: int = 112) -> tuple[int, dict, bytes]:
    """同步调用 ASGI app（SCF 主线程无 event loop，需自行管理）。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # 有活跃 loop → nest_asyncio 或 run_in_executor
        import nest_asyncio
        nest_asyncio.apply()
        coro = _call_asgi(
            _asgi_scope_to_request(method, path, query, headers, body),
            body,
        )
        return loop.run_until_complete(coro)

    # 无活跃 loop → 创建新 loop
    coro = _call_asgi(
        _asgi_scope_to_request(method, path, query, headers, body),
        body,
    )
    return asyncio.run(asyncio.wait_for(coro, timeout=timeout))


# ─────────────────── SCF 入口 ───────────────────

def scf_handler(event: dict, context: Any) -> dict:
    """腾讯云函数主入口（HTTP 触发器）。

    事件格式（SCF 直传）:
        event = {
            "requestContext": {"httpMethod": "POST", "path": "/api/generate"},
            "headers": {"content-type": "application/json"},
            "body": '{"key": "value"}',
            "isBase64Encoded": False,
            "queryString": {"page": "1"},   # SCF API 网关
            # 或者 queryStringParameters: {"page": "1"}  # SCF 函数直调
        }

    调用端透传:
        * SCF + API 网关 → "queryString" (dict)
        * SCF + 函数直调 → "queryStringParameters" (dict)
    """
    # ── 解析 SCF HTTP 事件 ──
    ctx = event.get("requestContext", {})
    method = (ctx.get("httpMethod") or event.get("httpMethod", "GET")).upper()
    path = ctx.get("path", "/") or "/"

    # 查询参数（兼容两种 SCF 事件格式）
    qs = ctx.get("queryString") or event.get("queryStringParameters") or {}
    query = ""
    if qs:
        from urllib.parse import urlencode
        query = "?" + urlencode(qs)

    # Headers（统一为小写 key）
    headers = {str(k).lower(): str(v) for k, v in event.get("headers", {}).items()}
    headers.setdefault("content-type", "application/json")

    # Body
    raw_body = event.get("body", "") or ""
    if event.get("isBase64Encoded"):
        import base64
        body = base64.b64decode(raw_body)
    else:
        body = raw_body.encode("utf-8")

    # ── 调用 FastAPI pipeline ──
    try:
        status, resp_headers, resp_body = _call_asgi_sync(
            method=method, path=path, query=query,
            headers=headers, body=body,
            timeout=int(event.get("timeout", 112)),
        )
    except Exception as exc:
        import traceback
        traceback.print_exc()
        status, resp_headers, resp_body = 500, {"content-type": "application/json"}, (
            json.dumps({"detail": f"SCF handler error: {type(exc).__name__}: {exc}"}).encode()
        )

    # ── 构造 SCF 响应 ──
    resp_body_str = resp_body.decode("utf-8") if isinstance(resp_body, (bytes, bytearray)) else str(resp_body)
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": resp_body_str,
    }


# ─────────────────── 同步执行工具 ───────────────────

def run_pipeline_sync(task_id: str, payload: dict) -> dict:
    """在 SCF 函数主体内同步跑完整 pipeline 并返回结果。

    调用方式:
        result = run_pipeline_sync(task_id, payload)
        return {"statusCode": 200, "body": json.dumps(result)}

    ⚠️ 注意: 真实 AI 模式约 20-30s，务必确认 SCF 超时 >= 60s。
    """
    from app.main import get_client
    from app.orchestrator import run_pipeline
    from app.schemas import GenerateRequest, TaskStatus

    client = get_client()
    task = None
    for t in __import__("app.main").main.task_store.list_tasks():
        if t.task_id == task_id:
            task = t
            break

    if task is None:
        return {"error": f"task not found: {task_id}"}

    asyncio.run(run_pipeline(task, client))
    if task.status == TaskStatus.done:
        try:
            from app.file_store import persist_task
            persist_task(task)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("persist task failed")

    return task.model_dump()
