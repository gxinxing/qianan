"""工具注册表：内置工具 + skill 安装时动态注册的 prompt 型工具。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional


@dataclass
class ToolSpec:
    """一个可被 Agent 调用的工具。

    handler 为 async 函数（同步函数请用 asyncio.to_thread 包一层），
    入参对应 parameters 声明的字段，返回字符串结果回传给模型。
    """

    name: str
    description: str
    parameters: dict
    handler: Callable[..., Awaitable[str]]
    source: str = "builtin"  # builtin / 技能名


_REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> None:
    _REGISTRY[spec.name] = spec


def unregister(name: str) -> bool:
    return _REGISTRY.pop(name, None) is not None


def get(name: str) -> Optional[ToolSpec]:
    return _REGISTRY.get(name)


def all_tools() -> list[ToolSpec]:
    return list(_REGISTRY.values())


def openai_schema(specs: list[ToolSpec]) -> list[dict]:
    """转成 OpenAI tools 参数格式。"""
    return [
        {
            "type": "function",
            "function": {
                "name": s.name,
                "description": s.description,
                "parameters": s.parameters,
            },
        }
        for s in specs
    ]
