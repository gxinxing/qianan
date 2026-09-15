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
