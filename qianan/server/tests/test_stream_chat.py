"""token 级流式 chat 的解析、聚合与降级测试。

验收：
  - SSE chunk 解析：content delta 顺序回调、tool_calls 分片聚合为完整调用
  - 非 200 / 连接失败 → _StreamUnsupported（契约：抛出时未推过任何 delta）
  - 工具循环：客户端支持流式 → on_text_delta 被调用；抛 _StreamUnsupported → 降级非流式
  - 无流式能力的客户端（旧 fake/mock）→ 行为与改造前完全一致（零回归）
"""
from __future__ import annotations

import asyncio
import json

import app.bailian.client as bc
from app.agent_core.loop import run_tool_loop
from app.agent_core.registry import ToolSpec
from app.bailian.client import BailianClient, _StreamUnsupported

# ---------------------------------------------------------------- 替身


async def _ok_handler(**_kwargs):
    return "ok"


class _FakeResp:
    """模拟 requests 流式响应：iter_lines 逐行产出 SSE。"""

    def __init__(self, lines, status_code=200, text=""):
        self._lines = lines
        self.status_code = status_code
        self.text = text

    def iter_lines(self, decode_unicode=False):
        yield from self._lines

    def json(self):
        return json.loads(self.text) if self.text else {}


def _sse(*chunks) -> list[str]:
    return [f"data: {json.dumps(c, ensure_ascii=False)}" for c in chunks] + ["data: [DONE]"]


def _install_fake_post(monkeypatch, resp):
    def _fake_post(*_a, **_k):
        return resp

    monkeypatch.setattr(bc._session, "post", _fake_post)


# ---------------------------------------------------------------- 1. 解析与聚合


def test_stream_parses_content_deltas_in_order(monkeypatch):
    """content delta 按到达顺序回调，聚合 content 完整。"""
    resp = _FakeResp(
        _sse(
            {"choices": [{"delta": {"content": "便携"}}]},
            {"choices": [{"delta": {"content": "榨汁杯"}}]},
            {"choices": [{"delta": {"content": "已上架"}}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        )
    )
    _install_fake_post(monkeypatch, resp)
    deltas: list[str] = []
    msg = BailianClient().chat_with_tools_stream([], [], on_delta=deltas.append)
    assert deltas == ["便携", "榨汁杯", "已上架"], f"增量顺序错乱: {deltas}"
    assert msg["content"] == "便携榨汁杯已上架"
    assert msg["tool_calls"] == []


def test_stream_aggregates_tool_call_fragments(monkeypatch):
    """tool_calls 分片（id/name/arguments 逐段到达）聚合为完整调用——与非流式同构。"""
    resp = _FakeResp(
        _sse(
            {"choices": [{"delta": {"content": "我来生成文案。"}}]},
            {"choices": [{"delta": {"tool_calls": [
                {"index": 0, "id": "call_1", "function": {"name": "generate_copy", "arguments": '{"plat'}}
            ]}}]},
            {"choices": [{"delta": {"tool_calls": [
                {"index": 0, "function": {"arguments": 'form": "ama'}}
            ]}}]},
            {"choices": [{"delta": {"tool_calls": [
                {"index": 0, "function": {"arguments": 'zon"}'}}
            ]}}]},
        )
    )
    _install_fake_post(monkeypatch, resp)
    msg = BailianClient().chat_with_tools_stream([], [], on_delta=lambda _t: None)
    assert msg["content"] == "我来生成文案。"
    assert len(msg["tool_calls"]) == 1
    call = msg["tool_calls"][0]
    assert call["id"] == "call_1"
    assert call["function"]["name"] == "generate_copy"
    assert json.loads(call["function"]["arguments"]) == {"platform": "amazon"}, call


def test_stream_ignores_reasoning_and_unknown_lines(monkeypatch):
    """reasoning_content 不外泄给用户；非 data: 行与心跳注释被跳过。"""
    resp = _FakeResp(
        [
            ": keep-alive",
            "",
            'data: {"choices":[{"delta":{"reasoning_content":"内部思考不该推给用户"}}]}',
            'data: {"choices":[{"delta":{"content":"可见"}}]}',
            'data: {"choices":[{"delta":{"content":"文本"}}]}',
            "data: [DONE]",
        ]
    )
    _install_fake_post(monkeypatch, resp)
    deltas: list[str] = []
    msg = BailianClient().chat_with_tools_stream([], [], on_delta=deltas.append)
    assert deltas == ["可见", "文本"]
    assert msg["content"] == "可见文本"
    assert "内部思考" not in json.dumps(msg, ensure_ascii=False)


# ---------------------------------------------------------------- 2. 降级契约


def test_stream_unsupported_on_non_200(monkeypatch):
    """非 200（网关无流式/参数不识）→ _StreamUnsupported，且未推过任何 delta。"""
    _install_fake_post(monkeypatch, _FakeResp([], status_code=400, text='{"error":"stream not supported"}'))
    deltas: list[str] = []
    try:
        BailianClient().chat_with_tools_stream([], [], on_delta=deltas.append)
    except _StreamUnsupported:
        pass
    else:
        raise AssertionError("非 200 应抛 _StreamUnsupported")
    assert deltas == [], "抛出 _StreamUnsupported 前不能推过 delta（否则降级会重复）"


def test_stream_unsupported_on_connection_error(monkeypatch):
    import requests

    def _boom(*_a, **_k):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(bc._session, "post", _boom)
    try:
        BailianClient().chat_with_tools_stream([], [], on_delta=lambda _t: None)
    except _StreamUnsupported:
        pass
    else:
        raise AssertionError("连接失败应抛 _StreamUnsupported")


# ---------------------------------------------------------------- 3. 工具循环集成


class _StreamingClient:
    """支持流式的替身：先流式叙述，再返回一个工具调用，最后收敛。"""

    is_mock = False
    supports_vision = False

    def __init__(self):
        self.calls = 0
        self.deltas: list[str] = []

    def chat_with_tools_stream(self, messages, tools, model=None, on_delta=None):
        self.calls += 1
        for piece in ["我先", "理解商品"]:
            if on_delta:
                on_delta(piece)
                self.deltas.append(piece)
        if self.calls == 1:
            return {
                "content": "我先理解商品",
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "noop", "arguments": "{}"}}
                ],
            }
        return {"content": "完成", "tool_calls": []}

    def chat_with_tools(self, messages, tools, model=None):
        raise AssertionError("客户端支持流式时不应走非流式路径")


def test_loop_uses_stream_and_forwards_deltas(monkeypatch):
    """工具循环优先流式：delta 实时回调，聚合消息驱动工具调用。"""
    client = _StreamingClient()
    out_deltas: list[str] = []
    tools = [ToolSpec(name="noop", description="noop", parameters={"type": "object", "properties": {}},
                      handler=_ok_handler)]
    result = asyncio.run(
        run_tool_loop(client, "sys", "user", tools, max_rounds=3, on_text_delta=out_deltas.append)
    )
    assert out_deltas[:2] == ["我先", "理解商品"]
    assert result["content"] == "完成"
    assert result["rounds"] == 2
    assert result["tool_results"].get("noop") == ["ok"]


class _UnsupportedStreamClient:
    """流式不被网关支持：抛 _StreamUnsupported，循环应降级非流式。"""

    is_mock = False
    supports_vision = False

    def __init__(self):
        self.fallback_called = 0

    def chat_with_tools_stream(self, messages, tools, model=None, on_delta=None):
        raise _StreamUnsupported("网关返回 400: stream not supported")

    def chat_with_tools(self, messages, tools, model=None):
        self.fallback_called += 1
        return {"content": "非流式兜底", "tool_calls": []}


def test_loop_falls_back_to_non_stream(monkeypatch):
    """_StreamUnsupported → 自动降级非流式，循环正常收敛（零回归）。"""
    client = _UnsupportedStreamClient()
    result = asyncio.run(
        run_tool_loop(
            client, "sys", "user",
            [ToolSpec(name="noop", description="n", parameters={"type": "object", "properties": {}},
                      handler=_ok_handler)],
            max_rounds=1, on_text_delta=lambda _t: None,
        )
    )
    assert client.fallback_called == 1, "应降级调用非流式"
    assert result["content"] == "非流式兜底"


class _LegacyClient:
    """无流式能力的老客户端（现有 fake/mock 形态）——应走非流式，行为不变。"""

    is_mock = False
    supports_vision = False

    def __init__(self):
        self.called = 0

    def chat_with_tools(self, messages, tools, model=None):
        self.called += 1
        return {"content": "老路径", "tool_calls": []}


def test_loop_legacy_client_unchanged():
    client = _LegacyClient()
    result = asyncio.run(
        run_tool_loop(
            client, "sys", "user",
            [ToolSpec(name="noop", description="n", parameters={"type": "object", "properties": {}},
                      handler=_ok_handler)],
            max_rounds=1, on_text_delta=lambda _t: None,
        )
    )
    assert client.called == 1
    assert result["content"] == "老路径"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
