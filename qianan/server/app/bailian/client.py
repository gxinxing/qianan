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


class BailianLike(Protocol):
    is_mock: bool
    supports_vision: bool

    def chat(self, system: str, user: str, model: str | None = None) -> str: ...

    def chat_with_tools(self, messages: list[dict], tools: list[dict], model: str | None = None) -> dict: ...

    def image_gen(self, prompt: str, model: str | None = None, ref_image: str | None = None) -> str: ...

    def vision(self, image_ref: str, prompt: str, model: str | None = None) -> str: ...


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['BAILIAN_API_KEY']}",
        "Content-Type": "application/json",
    }


def _post(payload: dict) -> dict:
    resp = requests.post(f"{BASE_URL}/chat/completions", headers=_headers(), json=payload, timeout=TIMEOUT)
    data = resp.json()
    if resp.status_code != 200 or "error" in data or (isinstance(data.get("code"), str) and "output" not in data):
        raise RuntimeError(f"百炼调用失败({resp.status_code}): {json.dumps(data, ensure_ascii=False)[:300]}")
    return data


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
        """图片生成：走 chat 路由 + DashScope 列表 content 格式。

        传入 ref_image（URL 或 data URL）时即以图改图：参考图作为
        {"image": ref} 追加进 content 列表（与 qianwen-agent 同款方案，已实测可用）。
        """
        content: list[dict] = [{"text": prompt}]
        if ref_image:
            content.append({"image": ref_image})
        data = _post(
            {
                "model": model or IMAGE_MODEL,
                "messages": [{"role": "user", "content": content}],
            }
        )
        result = data["output"]["choices"][0]["message"]["content"]
        for part in result:
            if isinstance(part, dict) and part.get("image"):
                return part["image"]
        raise RuntimeError(f"图片生成返回中未找到图片: {str(result)[:200]}")

    def vision(self, image_ref: str, prompt: str, model: str | None = None) -> str:
        """视觉理解：网关暂无 VL 模型，仅在显式配置 QIANAN_VL_MODEL 时尝试。"""
        if not VL_MODEL:
            raise NotImplementedError("当前网关无视觉理解模型，请配置 QIANAN_VL_MODEL 或使用文本理解路径")
        data = _post(
            {
                "model": model or VL_MODEL,
                "enable_thinking": False,
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
