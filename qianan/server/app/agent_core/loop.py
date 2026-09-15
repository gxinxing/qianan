"""function calling 工具循环：模型决定调什么工具，循环执行直到收敛或超限。

兜底原则：任何异常/不收敛都返回 fallback 标志，由调用方走确定性路径。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from ..bailian.client import BailianLike
from .registry import ToolSpec, openai_schema

logger = logging.getLogger(__name__)

TOOL_RESULT_LIMIT = 2000


async def run_tool_loop(
    client: BailianLike,
    system: str,
    user: str,
    tools: list[ToolSpec],
    max_rounds: int = 3,
    deadline_s: float = 40.0,
    on_event=None,
    should_stop=None,
) -> dict:
    """执行工具循环。

    返回 {
      "content": 最终文本（收敛时）, "tool_results": {工具名: [结果...]},
      "rounds": 轮数, "fallback": 是否未收敛/异常（调用方应走兜底路径）,
      "reason": 兜底原因, "cancelled": 是否被用户取消
    }

    should_stop: 返回 True 时立即停止。用于「用户点了停止」时真正中断后台 Agent ——
    否则断开前端 fetch 只是不再接收事件，模型调用仍在继续烧额度。
    """
    result = {
        "content": None,
        "tool_results": {},
        "rounds": 0,
        "fallback": False,
        "reason": "",
        "cancelled": False,
    }
    stop_check = should_stop or (lambda: False)
    if not tools:
        result["fallback"], result["reason"] = True, "无可用工具"
        return result
    deadline = time.monotonic() + deadline_s
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    schemas = openai_schema(tools)
    handlers = {t.name: t.handler for t in tools}

    for rnd in range(max_rounds):
        # 用户取消：优先于墙钟判断，立即停止，不再发起任何模型调用
        if stop_check():
            result["cancelled"], result["reason"] = True, "用户取消"
            return result
        if time.monotonic() >= deadline:
            result["fallback"], result["reason"] = True, f"超墙钟预算 {deadline_s:.0f}s"
            return result
        try:
            msg = await asyncio.to_thread(client.chat_with_tools, messages, schemas)
        except Exception as exc:  # noqa: BLE001 —— 网关异常即回退
            logger.warning("工具循环网关异常：%s", exc)
            result["fallback"], result["reason"] = True, f"网关异常: {exc}"
            return result

        calls = msg.get("tool_calls") or []
        if not calls:
            result["content"] = msg.get("content") or ""
            result["rounds"] = rnd + 1
            return result

        messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": calls})
        for call in calls:
            # 单个工具就可能是几十秒的图像/视频生成，逐个检查才能及时停
            if stop_check():
                result["cancelled"], result["reason"] = True, "用户取消"
                return result
            fn = call.get("function") or {}
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            handler = handlers.get(name)
            if handler is None:
                out = f"未知工具: {name}"
            else:
                try:
                    out = str(await handler(**args))
                except Exception as exc:  # noqa: BLE001 —— 单工具失败不炸整个循环
                    logger.warning("工具 %s 执行失败：%s", name, exc)
                    out = f"工具执行失败: {exc}"
            result["tool_results"].setdefault(name, []).append(out)
            if on_event:
                try:
                    on_event(name, args, out)
                except Exception:  # noqa: BLE001
                    pass
            messages.append(
                {"role": "tool", "tool_call_id": call.get("id", ""), "content": out[:TOOL_RESULT_LIMIT]}
            )
        result["rounds"] = rnd + 1

    result["fallback"], result["reason"] = True, f"超过最大轮数 {max_rounds}"
    return result
