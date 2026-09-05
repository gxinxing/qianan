"""商品图上公网临时图床，换取 AI 网关可访问的 http(s) URL。

背景：apimart 等聚合网关的图片任务接口拒绝超大体 data URL（nginx 413，
实测 >~2MB body 被拒），而本地 localhost URL 网关服务器无法回访。
因此用户浏览器上传的 base64 图，先解码 POST 到免登录临时图床（litterbox，
1h–72h 有效），再把返回 URL 交给管线（VL 识别 / 以图改图 / 下载落盘都走 URL）。
"""
from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger(__name__)

LITTERBOX_API = "https://litterbox.catbox.moe/resources/internals/api.php"
RETRIES = 2


def upload_bytes(data: bytes, filename: str = "product.png", ttl: str = "24h") -> str:
    """上传图片字节，返回公网 URL。ttl: 1h / 12h / 24h / 72h。"""
    last_err: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            resp = requests.post(
                LITTERBOX_API,
                files={"fileToUpload": (filename, data, "image/png")},
                data={"reqtype": "fileupload", "time": ttl},
                timeout=90,
            )
            text = (resp.text or "").strip()
            if resp.status_code == 200 and text.startswith("https://"):
                return text
            last_err = RuntimeError(f"图床上传失败({resp.status_code}): {text[:200]}")
        except Exception as exc:  # noqa: BLE001
            last_err = exc
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"图床上传重试 {RETRIES} 次仍失败: {last_err}")
