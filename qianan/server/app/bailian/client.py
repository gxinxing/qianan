"""阿里云百炼客户端封装 —— 黑客松 Token Plan 专属网关（真实模式 + Mock 模式）。

实测结论（2026-09-01，Token Plan 专属基地址）：
1. 文本模型走 /chat/completions（OpenAI 兼容），支持 enable_thinking: false 关闭思考加速响应。
2. 图片生成模型（qwen-image-2.0 / wan2.7-image）同样走 /chat/completions，
   但 content 必须是 DashScope 列表格式 [{"text": "..."}]，
   图片 URL 在返回体的 choices[0].message.content[0]["image"]。
   （/images/generations 路由在该网关不可用。）
3. 该网关暂无视觉理解（VL）模型：商品理解默认纯文本路径；
   如未来配置 QIANAN_VL_MODEL，将尝试多模态调用。
4. 以图改图（图片编辑）已实测可用：content 列表追加 {"image": 参考图URL}，
   模型按提示词对参考图改写（白底化/场景化），保持商品本体不变。
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from typing import Protocol

import requests

logger = logging.getLogger(__name__)


def _load_server_env() -> None:
    """从 server/.env 加载配置（不覆盖已存在的环境变量）。"""
    from pathlib import Path

    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_server_env()

BASE_URL = os.getenv(
    "BAILIAN_BASE_URL", "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
)
TEXT_MODEL = os.getenv("QIANAN_TEXT_MODEL", "qwen3.7-max")
IMAGE_MODEL = os.getenv("QIANAN_IMAGE_MODEL", "qwen-image-2.0")
VL_MODEL = os.getenv("QIANAN_VL_MODEL", "")  # 留空 = 网关无 VL 模型
TIMEOUT = 180
# —— HTTP 重试：百炼网关偶发 429/5xx/超时抖动，避免整条 pipeline 因此直接失败 ——
_MAX_ATTEMPTS = 3       # 最多重试 2 次，共 3 次尝试
_RETRY_BACKOFF = 1.0     # 指数退避基数：两次重试分别等待约 1s / 2s（另加随机 jitter）
_RETRY_AFTER_CAP = 60.0  # 429 优先按 Retry-After 头等待，并截断到该上限（秒）


class BailianLike(Protocol):
    is_mock: bool
    supports_vision: bool

    def chat(self, system: str, user: str, model: str | None = None) -> str: ...

    def chat_with_tools(self, messages: list[dict], tools: list[dict], model: str | None = None) -> dict: ...

    def image_gen(self, prompt: str, model: str | None = None, ref_image: str | None = None) -> str: ...

    def vision(self, image_ref: str, prompt: str, model: str | None = None) -> str: ...


class _AsyncImageUnsupported(RuntimeError):
    """网关不支持异步 images/generations 任务接口（用于回退 DashScope chat 格式）。"""


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['BAILIAN_API_KEY']}",
        "Content-Type": "application/json",
    }


def _resp_preview(resp) -> str:
    """响应体预览（用于错误信息）：能解析为 JSON 则序列化，否则取纯文本前 300 字符。"""
    try:
        return json.dumps(resp.json(), ensure_ascii=False)[:300]
    except ValueError:
        return (resp.text or "")[:300]


def _retry_delay(resp, attempt: int) -> float:
    """第 attempt 次尝试失败后的等待秒数：429 优先按 Retry-After 头，其余指数退避 + jitter。"""
    if resp is not None and resp.status_code == 429:
        raw = (resp.headers.get("Retry-After") or "").strip()
        if raw:
            try:
                after = float(raw)
                if after >= 0:
                    return min(after, _RETRY_AFTER_CAP)
            except ValueError:
                pass  # HTTP-date 等非数字格式 → 退回指数退避
    return _RETRY_BACKOFF * (2 ** (attempt - 1)) + random.uniform(0, 0.5)


def _post(payload: dict) -> dict:
    # 显式非流式：部分兼容网关（如 apimart.ai）在未传 stream 时默认返回 SSE
    # 分块，导致 resp.json() 解析崩溃。统一置 False 请求标准一次性 JSON。
    payload.setdefault("stream", False)
    url = f"{BASE_URL}/chat/completions"
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(url, headers=_headers(), json=payload, timeout=TIMEOUT)
        except (requests.Timeout, requests.ConnectionError) as exc:
            # 超时/连接错误：网关瞬时抖动所致；chat 推理接口无服务端副作用，重发安全。
            # 重试耗尽后保留原始异常类型原样抛出（与旧版行为一致）。
            if attempt == _MAX_ATTEMPTS:
                raise
            delay = _retry_delay(None, attempt)
            logger.warning(
                "百炼调用第 %d/%d 次尝试网络异常(%s): %s；%.1fs 后重试",
                attempt, _MAX_ATTEMPTS, type(exc).__name__, exc, delay,
            )
            time.sleep(delay)
            continue
        status = resp.status_code
        if status == 429 or status >= 500:
            # 明确可重试：限流/网关侧 5xx —— 请求被拒绝或未触达业务逻辑，均无副作用。
            if attempt == _MAX_ATTEMPTS:
                raise RuntimeError(f"百炼调用失败({status}): {_resp_preview(resp)}")
            delay = _retry_delay(resp, attempt)
            logger.warning(
                "百炼调用第 %d/%d 次尝试失败(%s): %s；%.1fs 后重试",
                attempt, _MAX_ATTEMPTS, status, _resp_preview(resp), delay,
            )
            resp.close()
            time.sleep(delay)
            continue
        # 其余状态码（200 正常 / 400、401 等明确参数或鉴权错误）不可重试；
        # JSON 解析失败同样不重试，维持原有解析与报错行为。
        data = resp.json()
        if status != 200 or "error" in data or (isinstance(data.get("code"), str) and "output" not in data):
            raise RuntimeError(f"百炼调用失败({status}): {json.dumps(data, ensure_ascii=False)[:300]}")
        return data
    raise RuntimeError("百炼调用失败：重试循环意外退出")  # 防御性兜底，正常流程不可达


def _message_content(data: dict):
    """兼容 DashScope(output.choices) 与 OpenAI(chat/completions, choices) 两种返回结构，取出 message.content。"""
    choices = None
    if isinstance(data.get("output"), dict):
        choices = data["output"].get("choices")
    if not isinstance(choices, list) and isinstance(data.get("choices"), list):
        choices = data["choices"]
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(f"网关返回中无 choices: {str(data)[:200]}")
    return choices[0]["message"]["content"]


class BailianClient:
    """真实网关调用（同步；Agent 层用 asyncio.to_thread 包装）。"""

    is_mock = False

    def __init__(self) -> None:
        if not os.environ.get("BAILIAN_API_KEY"):
            raise RuntimeError("BAILIAN_API_KEY 未配置")

    @property
    def supports_vision(self) -> bool:
        return bool(VL_MODEL)

    def chat(self, system: str, user: str, model: str | None = None) -> str:
        data = _post(
            {
                "model": model or TEXT_MODEL,
                "enable_thinking": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        )
        return data["choices"][0]["message"]["content"]

    def chat_with_tools(self, messages: list[dict], tools: list[dict], model: str | None = None) -> dict:
        """function calling：返回 assistant message（content 与 tool_calls 均可能为空/非空）。"""
        data = _post(
            {
                "model": model or TEXT_MODEL,
                "enable_thinking": False,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
            }
        )
        return data["choices"][0]["message"]

    def image_gen(self, prompt: str, model: str | None = None, ref_image: str | None = None) -> str:
        """图片生成，兼容两类网关：

        1. apimart.ai 等 OpenAI 兼容聚合网关：POST /images/generations 提交异步
           T2I 任务 → 轮询 GET /tasks/{id}（支持 image_url 参考图 = 以图改图）。
        2. 官方 token-plan（DashScope compatible-mode）：/images/generations 不可用，
          须走 /chat/completions + content 列表 [{"text":...}, {"image": ref}]；
          该方法失败时自动回退该路径。
        """
        model = model or IMAGE_MODEL
        try:
            return self._async_image_gen(prompt, model, ref_image)
        except _AsyncImageUnsupported:
            pass  # 网关不支持异步任务接口 → 回退 DashScope chat 格式
        content: list[dict] = [{"text": prompt}]
        if ref_image:
            content.append({"image": ref_image})
        data = _post(
            {
                "model": model,
                "messages": [{"role": "user", "content": content}],
            }
        )
        result = _message_content(data)
        if isinstance(result, str):
            return result
        for part in result:
            if isinstance(part, dict) and part.get("image"):
                return part["image"]
        raise RuntimeError(f"图片生成返回中未找到图片: {str(result)[:200]}")

    def _async_image_gen(self, prompt: str, model: str, ref_image: str | None) -> str:
        """异步任务式图片生成（apimart 等聚合网关），含提交与轮询。"""
        payload: dict = {"model": model, "prompt": prompt, "n": 1, "size": "1024x1024"}
        if ref_image:
            payload["image_url"] = ref_image
        resp = requests.post(
            f"{BASE_URL}/images/generations", headers=_headers(), json=payload, timeout=120
        )
        try:
            data = resp.json()
        except ValueError as exc:
            raise _AsyncImageUnsupported(f"images/generations 非 JSON: {exc}") from exc
        if resp.status_code != 200 or "task_id" not in json.dumps(data, ensure_ascii=False):
            # 网关无该路由（如官方 token-plan）或任务提交失败
            err = str(data)[:200] if resp.status_code not in (404, 405) else "route not found"
            if resp.status_code in (404, 405):
                raise _AsyncImageUnsupported(err)
            raise RuntimeError(f"图片任务提交失败({resp.status_code}): {err}")
        tasks = (data.get("data") or [{}])
        tid = (tasks[0] if isinstance(tasks, list) else tasks).get("task_id") if tasks else None
        if not tid:
            raise RuntimeError(f"图片任务提交无 task_id: {str(data)[:200]}")

        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            time.sleep(4)
            r = requests.get(f"{BASE_URL}/tasks/{tid}", headers=_headers(), timeout=30)
            try:
                d = (r.json() or {}).get("data") or {}
            except ValueError:
                continue
            status = d.get("status")
            if status == "completed":
                imgs = ((d.get("result") or {}).get("images") or [])
                if imgs:
                    url = (imgs[0].get("url") or "")
                    if isinstance(url, list):
                        url = url[0] if url else ""
                    if url:
                        return url
                raise RuntimeError(f"图片任务完成但无 URL: {str(d)[:200]}")
            if status in ("failed", "error", "cancelled"):
                raise RuntimeError(
                    f"图片任务 {status}: {d.get('error') or d.get('message') or '上游错误'}"
                )
        raise RuntimeError(f"图片生成超时（180s）: task {tid}")

    def vision(self, image_ref: str, prompt: str, model: str | None = None) -> str:
        """视觉理解：在显式配置 QIANAN_VL_MODEL 时使用（如 apimart gpt-4o）。

        注意：不能带 enable_thinking 等 DashScope 专属参数（OpenAI 兼容模型 400）。
        """
        if not VL_MODEL:
            raise NotImplementedError("当前网关无视觉理解模型，请配置 QIANAN_VL_MODEL 或使用文本理解路径")
        data = _post(
            {
                "model": model or VL_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": image_ref}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            }
        )
        message = data["choices"][0]["message"]
        content = message.get("content")
        if isinstance(content, list):
            return "".join(p.get("text", "") for p in content if isinstance(p, dict))
        return str(content)


class MockBailianClient:
    """模拟客户端：返回可读占位结果，供无 key 联调与演示兜底。"""

    is_mock = True
    supports_vision = False

    def chat(self, system: str, user: str, model: str | None = None) -> str:
        return f"[MOCK chat] 已收到指令（前 80 字）：{user[:80]}……"

    def chat_with_tools(self, messages: list[dict], tools: list[dict], model: str | None = None) -> dict:
        """脚本化工具调用：收到 tool 结果即收敛；否则对第一个工具发一次空参调用。"""
        if any(m.get("role") == "tool" for m in messages[-2:]):
            return {"content": "[MOCK] 工具循环已收敛", "tool_calls": []}
        if tools:
            fn = tools[0]["function"]
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": f"mock_call_{len(messages)}",
                        "type": "function",
                        "function": {"name": fn["name"], "arguments": "{}"},
                    }
                ],
            }
        return {"content": "[MOCK] 无工具可用", "tool_calls": []}

    def image_gen(self, prompt: str, model: str | None = None, ref_image: str | None = None) -> str:
        return "mock://generated-image"

    def vision(self, image_ref: str, prompt: str, model: str | None = None) -> str:
        return "[MOCK vision] 模拟商品理解结果。"


def get_client() -> BailianLike:
    if os.getenv("QIANAN_MOCK", "0") == "1":
        logger.warning("QIANAN_MOCK=1，使用模拟百炼客户端")
        return MockBailianClient()
    if not os.getenv("BAILIAN_API_KEY"):
        logger.warning("未配置 BAILIAN_API_KEY，自动进入 Mock 模式")
        return MockBailianClient()
    return BailianClient()


def resolve_image_ref(image_url: str | None, image_base64: str | None) -> str | None:
    """把上传图转为模型可用的引用：URL 直接用，base64 转 data URL；都没有则返回 None。"""
    if image_url:
        return image_url
    if image_base64:
        data = image_base64.split(",", 1)[-1]
        return f"data:image/jpeg;base64,{data}"
    return None
