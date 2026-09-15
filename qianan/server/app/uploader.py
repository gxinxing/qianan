"""商品图上公网临时图床，换取 AI 网关可访问的 http(s) URL。

背景：apimart 等聚合网关的图片任务接口拒绝超大体 data URL（nginx 413，
实测 >~2MB body 被拒），而本地 localhost URL 网关服务器无法回访。
因此用户浏览器上传的 base64 图，先解码 POST 到免登录临时图床（litterbox，
1h–72h 有效），再把返回 URL 交给管线（VL 识别 / 以图改图 / 下载落盘都走 URL）。
"""
from __future__ import annotations

import logging
import threading
import time

import requests

logger = logging.getLogger(__name__)

LITTERBOX_API = "https://litterbox.catbox.moe/resources/internals/api.php"
RETRIES = 2
#: 单次上传超时。曾被设为 90s —— 图床不可用时每张图都要白等 90s×3。
#: litterbox 是国外免费图床，对数据中心 IP（云函数出口）会直接拒绝，
#: 长超时只是把失败等得更久，并不能换来成功，故收紧到 15s。
TIMEOUT_S = 15
#: 可用性熔断：同一进程内连续失败达到该次数后不再尝试上传，直接快速失败。
#: 背景（2026-09-15 实测）：litterbox 对所有请求返回 412 Precondition Failed，
#: 转存必然失败。调用方 `_persist_image` 已有「失败即退回原始 URL」的兜底，
#: 因此这里的正确行为是**尽快失败**而不是耐心重试 —— 不加熔断时，
#: 单次出图（主图+4 张详情图）仅白等就耗掉 384s，直接吃光 Agent 的墙钟预算。
_FAILURE_THRESHOLD = 2
_consecutive_failures = 0
_circuit_open = False
_lock = threading.Lock()


def is_circuit_open() -> bool:
    """图床是否已被熔断（供调用方跳过无谓的上传尝试）。"""
    return _circuit_open


def upload_bytes(data: bytes, filename: str = "product.png", ttl: str = "24h") -> str:
    """上传图片字节，返回公网 URL。ttl: 1h / 12h / 24h / 72h。

    图床不可用时快速失败（熔断），由调用方回退到原始 URL。
    """
    global _consecutive_failures, _circuit_open

    if _circuit_open:
        raise RuntimeError("图床已被熔断（连续上传失败），跳过上传并回退原始 URL")

    last_err: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            resp = requests.post(
                LITTERBOX_API,
                files={"fileToUpload": (filename, data, "image/png")},
                data={"reqtype": "fileupload", "time": ttl},
                timeout=TIMEOUT_S,
            )
            text = (resp.text or "").strip()
            if resp.status_code == 200 and text.startswith("https://"):
                with _lock:
                    _consecutive_failures = 0
                return text
            last_err = RuntimeError(f"图床上传失败({resp.status_code}): {text[:200]}")
        except Exception as exc:  # noqa: BLE001
            last_err = exc
        time.sleep(1.0 * (attempt + 1))

    with _lock:
        _consecutive_failures += 1
        if _consecutive_failures >= _FAILURE_THRESHOLD:
            _circuit_open = True
            logger.warning(
                "图床连续 %d 次上传失败，已熔断：后续图片将直接使用原始 URL（本次进程内不再重试）",
                _consecutive_failures,
            )
    raise RuntimeError(f"图床上传重试 {RETRIES} 次仍失败: {last_err}")
