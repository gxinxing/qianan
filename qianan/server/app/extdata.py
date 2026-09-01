"""外部数据消费层：连接器的「产品化出口」。

规划器能调工具只是第一步——真正的 AI 感来自核心模块主动消费实时数据：
- economics 用 live_fx() 替换写死的 7.2（保本价随真实汇率浮动）；
- ideation 用 hot_keywords() 把平台实时热搜注入选品 prompt（建议跟着趋势走）；
- competitor_band() 给选品建议附上类目竞品价格带（定价不再拍脑袋）。

每个函数三段式（点亮开关）：
  连接器已安装且调用成功 → 实时数据（source=live/demo）；
  未安装或调用失败 → 内置兜底（source=builtin/none），主流程永不断。
TTL 缓存避免每次测算都打外部 API；数据获取方式声明在连接器 manifest 里，
本模块只通过 registry 调用已注册工具——一次声明，规划器与核心引擎双路消费。
"""
from __future__ import annotations

import logging
import re
import time

from . import skill_store
from .agent_core import registry

logger = logging.getLogger(__name__)

# 连接器 ID / 工具名契约（与 data/skills/registry/*.json 清单一一对应）
FX_SKILL = "fx-live"
FX_TOOL = "get_fx_usd_cny"
TRENDS_SKILL = "trends-hot"
TRENDS_TOOL = "get_trending_searches"
COMPETITOR_SKILL = "competitor-band"
COMPETITOR_TOOL = "get_competitor_band"

FX_FALLBACK = 7.2  # 与 economics.USD_CNY 保持一致的内置兜底汇率

_FX_TTL = 3600  # 汇率 1 小时一刷
_TRENDS_TTL = 6 * 3600  # 热搜 6 小时一刷
_COMPETITOR_TTL = 24 * 3600  # 竞品带 24 小时一刷（static 数据本身不变，防重复解析）
_NEGATIVE_TTL = 300  # 兜底/失败结果只缓存 5 分钟——连接器恢复后快速自愈，不长时间卡在内置数据

_cache: dict[str, tuple[float, object]] = {}  # key → (过期时刻, 值)

_MARKET_GEO = {"us": "US", "sea": "SG", "global": "US"}


def _cached(key: str):
    hit = _cache.get(key)
    if hit and time.time() < hit[0]:
        return hit[1]
    return None


def _store(key: str, value, ttl: int) -> None:
    _cache[key] = (time.time() + ttl, value)


async def _call_tool(tool_name: str, **kwargs) -> str | None:
    """调用已注册连接器工具；未注册/报错/[connector-error] 一律返回 None（走兜底）。"""
    spec = registry.get(tool_name)
    if spec is None:
        return None
    try:
        result = await spec.handler(**kwargs)
    except Exception:  # noqa: BLE001 —— 连接器故障不许拖垮主流程
        logger.warning("连接器工具调用异常: %s", tool_name, exc_info=True)
        return None
    if not result or result.startswith("[connector-error]"):
        return None
    return result


async def live_fx() -> tuple[float, str]:
    """USD/CNY 汇率。(汇率, source)：source = live（实时）| builtin（内置 7.2）。"""
    cached = _cached("fx")
    if cached:
        return cached
    if skill_store.is_installed(FX_SKILL):
        raw = await _call_tool(FX_TOOL)
        if raw:
            try:
                rate = round(float(raw.strip().strip('"')), 4)
                if 5.0 < rate < 10.0:  # 合理性护栏：异常值宁可回退
                    result = (rate, "live")
                    _store("fx", result, _FX_TTL)
                    return result
            except ValueError:
                logger.warning("实时汇率解析失败: %s", raw[:80])
    result = (FX_FALLBACK, "builtin")
    _store("fx", result, _NEGATIVE_TTL)
    return result


async def hot_keywords(market: str) -> tuple[list[str], str]:
    """目标市场平台热搜词。(词条列表, source)：source = live | none（未装连接器/拉取失败）。"""
    key = f"trends:{market}"
    cached = _cached(key)
    if cached is not None:
        return cached
    words: list[str] = []
    source = "none"
    if skill_store.is_installed(TRENDS_SKILL):
        geo = _MARKET_GEO.get(market, "US")
        raw = await _call_tool(TRENDS_TOOL, geo=geo)
        if raw:
            # RSS/XML：第 1 个 <title> 是频道名，其后才是热搜条目
            titles = re.findall(r"<title>([^<]+)</title>", raw)
            seen: list[str] = []
            for t in titles[1:]:
                t = t.strip()
                if t and t not in seen:
                    seen.append(t)
            words = seen[:8]
            if words:
                source = "live"
    result = (words, source)
    _store(key, result, _TRENDS_TTL if words else _NEGATIVE_TTL)
    return result


async def competitor_band(category: str) -> tuple[dict | None, str]:
    """类目竞品价格带。(数据, source)：source = demo（演示连接器）| none。"""
    table = _cached("competitor")
    if table is None and skill_store.is_installed(COMPETITOR_SKILL):
        raw = await _call_tool(COMPETITOR_TOOL)
        if raw:
            import json

            try:
                table = json.loads(raw)
            except ValueError:
                logger.warning("竞品带数据解析失败: %s", raw[:80])
        _store("competitor", table, _COMPETITOR_TTL if table else _NEGATIVE_TTL)
    if isinstance(table, dict):
        band = table.get(category) or table.get("home_kitchen")
        if isinstance(band, dict):
            return band, "demo"
    return None, "none"
