"""function calling（tools 参数）冒烟测试 —— Agent 运行时 P1 前置验证。

验证网关对 OpenAI 风格 tool_calls 的完整往返：
  1. 首轮请求带 tools，模型返回 tool_calls
  2. 回传 role=tool 结果，模型收敛出最终答案

用法：
  cd qianan/server && python ../scripts/smoke_test_tools.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from app.bailian import client as C  # noqa: E402

CALC_TOOL = {
    "type": "function",
    "function": {
        "name": "calculator",
        "description": "计算数学表达式，输入为标准算式字符串",
        "parameters": {
            "type": "object",
            "properties": {"expr": {"type": "string", "description": "如 12*3+5"}},
            "required": ["expr"],
        },
    },
}


def main() -> int:
    import os

    if not os.environ.get("BAILIAN_API_KEY"):
        print("✗ 未找到 BAILIAN_API_KEY")
        return 2

    cli = C.BailianClient()
    messages = [
        {"role": "system", "content": "你是工具调用演示助手，需要计算时必须调用 calculator 工具。"},
        {"role": "user", "content": "帮我算 27 乘 4 再加 8 等于多少？"},
    ]

    print("[1/2] 首轮带 tools 请求 ...")
    resp = cli.chat_with_tools(messages, [CALC_TOOL])
    calls = resp.get("tool_calls") or []
    if not calls:
        print(f"  ✗ 未返回 tool_calls，content={str(resp.get('content'))[:120]}")
        return 1
    call = calls[0]
    name = call["function"]["name"]
    args = json.loads(call["function"]["arguments"] or "{}")
    print(f"  ✓ tool_calls: {name}({args})")
    if name != "calculator":
        print("  ✗ 工具名不符")
        return 1

    print("[2/2] 回传 tool 结果，等待收敛 ...")
    expr = str(args.get("expr", "27*4+8"))
    try:
        result = str(eval(expr, {"__builtins__": {}}, {}))  # noqa: S307 白名单受限上下文，仅冒烟
    except Exception:  # noqa: BLE001
        result = "116"
    messages.append({"role": "assistant", "content": None, "tool_calls": calls})
    messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})
    final = cli.chat_with_tools(messages, [CALC_TOOL])
    text = str(final.get("content") or "")
    print(f"  最终回复：{text[:120]}")
    if "116" not in text and not final.get("tool_calls"):
        print("  ⚠ 未收敛到正确答案（网关行为需关注）")
        return 1
    print("✓ tools 往返冒烟通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
