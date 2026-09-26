"""鉴权/额度/欠费类致命错误的识别 —— 决定系统能否优雅降级而不是硬崩。

回归背景（2026-09-15 实测）：
百炼账户欠费时返回 **HTTP 400 + code=Arrearage**，而判定逻辑当时只认 401/403
与 api_key_quota_exceeded。于是欠费被当成普通错误抛出，整条生成以 partial 收场 ——
而这类错误的正确处置是走 BailianAuthFatal，由 ResilientClient 降级 Mock 保住演示。

注意：欠费的 HTTP 状态码是 400，**不能只用状态码判断**，必须看响应体语义。
"""
from __future__ import annotations

import pytest

from app.bailian.client import _FATAL_MARKERS, _is_fatal_error

# ------------------------------------------------------------------ 应判为致命

@pytest.mark.parametrize("status", [401, 403])
def test_auth_status_codes_are_fatal(status):
    """401/403 一律致命，不看响应体。"""
    assert _is_fatal_error(status, "") is True


def test_quota_exceeded_is_fatal():
    """TokenDance 网关额度上限（实测返回）。"""
    body = '{"error": {"message": "API 密钥达到额度上限", "code": "api_key_quota_exceeded"}}'
    assert _is_fatal_error(403, body) is True


def test_arrearage_400_is_fatal():
    """百炼账户欠费：HTTP 400 + code=Arrearage，必须识别为致命。"""
    body = '{"code":"Arrearage","message":"Access denied, please make sure your account is in good standing."}'
    assert _is_fatal_error(400, body) is True


def test_overdue_payment_400_is_fatal():
    """欠费提示出现在 message 里的另一种写法。"""
    body = '{"error":{"message":"Access denied ... error-code#overdue-payment"}}'
    assert _is_fatal_error(400, body) is True


def test_free_quota_exhausted_is_fatal():
    """免费额度用尽（qwen3.7-plus 实测返回），重试同样无用。"""
    body = '{"error":{"message":"Free quota exhausted. To continue accessing the model on a paid basis..."}}'
    assert _is_fatal_error(400, body) is True


# ---------------------------------------------------------------- 不应判为致命

def test_plain_400_is_not_fatal():
    """参数错误（如 content 缺 type）属于可修正问题，重试/换格式可能有救 —— 不能降级。"""
    body = '{"error":{"message":"Missing required parameter:\'messages.[0].content[1].type\'."}}'
    assert _is_fatal_error(400, body) is False


def test_success_is_not_fatal():
    assert _is_fatal_error(200, '{"choices":[]}') is False


def test_404_route_missing_is_not_fatal():
    """路由不存在是可预期的（兼容模式没有 images 路由），不是致命错误。"""
    assert _is_fatal_error(404, "") is False


def test_marker_list_is_the_contract():
    """标记表本身是契约：改动必须是有意为之，且每条都要能命中真实响应体。"""
    assert "Arrearage" in _FATAL_MARKERS
    assert "api_key_quota_exceeded" in _FATAL_MARKERS
    assert "overdue-payment" in _FATAL_MARKERS


# ---------------------------------------------------------------- 生图与文本降级解耦


class _FatalChatClient:
    """chat 永远 fatal、image_gen 正常的替身：模拟云端「文本欠费 + 独立生图网关」。"""

    is_mock = False
    supports_vision = False

    def chat(self, system, user, model=None):
        from app.bailian.client import BailianAuthFatal

        raise BailianAuthFatal("百炼欠费(400): Arrearage")

    def chat_with_tools(self, messages, tools, model=None):
        raise RuntimeError("不应被调用")

    def image_gen(self, prompt, model=None, ref_image=None):
        return "https://image.apimart/real.png"

    def vision(self, image_ref, prompt, model=None):
        return ""

    def video_gen(self, image_url, prompt, model=None):
        return ""


def test_image_gen_survives_text_fatal_with_dedicated_gateway(monkeypatch):
    """独立生图网关（IMAGE_API_KEY）配置时：文本 fatal 降级后生图仍走真实链路。

    云端真实拓扑：文本网关欠费降级 Mock，apimart 生图（独立 key）不受牵连。
    """
    import app.bailian.client as bc
    from app.bailian.client import _ResilientClient

    monkeypatch.setattr(bc, "IMAGE_API_KEY", "sk-dedicated-image-key")
    rc = _ResilientClient(_FatalChatClient())

    with _catch_logger():
        rc.chat("s", "u")  # 文本 fatal → is_mock=True
    assert rc.is_mock is True

    # 生图不受文本降级牵连，仍返回真实 URL
    assert rc.image_gen("a red apple") == "https://image.apimart/real.png"
    assert rc.image_live is True


def test_image_gen_follows_text_downgrade_without_dedicated_gateway(monkeypatch):
    """未配置独立生图网关时保持历史行为：文本降级 → 生图一并 Mock。"""
    import app.bailian.client as bc
    from app.bailian.client import _ResilientClient

    monkeypatch.setattr(bc, "IMAGE_API_KEY", "")
    rc = _ResilientClient(_FatalChatClient())

    with _catch_logger():
        rc.chat("s", "u")  # 文本 fatal → is_mock=True
    assert rc.is_mock is True
    assert rc.image_live is False
    assert rc.image_gen("a red apple").startswith("mock://")  # 随文本降级


class _catch_logger:
    """吞掉降级 warning，保持测试输出干净。"""

    def __enter__(self):
        import logging

        logging.disable(logging.WARNING)
        return self

    def __exit__(self, *exc):
        import logging

        logging.disable(logging.NOTSET)
        return False
