"""指标回流 collector（PRD v0.3 · Feature 3：数据飞轮的回流段）。

把 mock 平台侧的经营数据拉回千岸，形成「生成 → 上架 → 回流 → 进化」闭环的回流段：
- collect_once()：遍历 live listings → 指标模拟器算到当前逻辑时钟 → 快照追加 metrics.jsonl
  （幂等：同一 (sku, logical_hours) 只写一次，反复调用不膨胀）
- latest()：每个 sku 取最新一条快照（数据看板与进化异常检测消费）
- history(sku)：单 sku 的回流时间线（画曲线用）
- 异常基线：CTR < 0.02 且累计曝光 ≥ 200（与 mock 页 warn 同源），打 anomaly 标记；
  异常即进化 Agent 的第三证据源（记忆/差评之外的经营信号）。
"""
from __future__ import annotations

import json
import threading
import time

from . import mock_seller
from .paths import writable_dir

DATA_DIR = writable_dir("data", "metrics")
METRICS_FILE = DATA_DIR / "metrics.jsonl"

CTR_ANOMALY_BASELINE = 0.02  # CTR 异常基线（跌破即视为标题/卖点不吸引）
MIN_IMPRESSIONS_FOR_ANOMALY = 200  # 曝光太小不判异常（避免上线初期误报）

_LOCK = threading.Lock()


def _read_all() -> list[dict]:
    if not METRICS_FILE.exists():
        return []
    rows: list[dict] = []
    for line in METRICS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _is_anomaly(row: dict) -> bool:
    """CTR 跌破基线且曝光量足够：判为经营异常（进化 Agent 的证据）。"""
    return bool(
        row.get("impressions", 0) >= MIN_IMPRESSIONS_FOR_ANOMALY
        and row.get("ctr", 1.0) < CTR_ANOMALY_BASELINE
    )


def collect_once(now: float | None = None) -> int:
    """对全部 live listing 各取一次当前快照，追加落盘（幂等）。返回新写入行数。"""
    now = now or time.time()
    rows = _read_all()
    seen = {(r.get("sku"), r.get("logical_hours")) for r in rows}
    new_rows: list[dict] = []
    for listing in mock_seller.list_listings():
        m = mock_seller.metrics_series(listing, now=now)
        key = (m["sku"], m["logical_hours"])
        if key in seen:
            continue
        seen.add(key)
        new_rows.append(
            {
                "ts": now,
                "sku": m["sku"],
                "listing_id": m["listing_id"],
                "platform": m["platform"],
                "logical_hours": m["logical_hours"],
                "title_quality": m["title_quality"],
                "impressions": m["totals"]["impressions"],
                "clicks": m["totals"]["clicks"],
                "ctr": m["totals"]["ctr"],
                "conversions": m["totals"]["conversions"],
            }
        )
    if new_rows:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            with open(METRICS_FILE, "a", encoding="utf-8") as f:
                for r in new_rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(new_rows)


def latest() -> list[dict]:
    """每个 sku 的最新快照（按上架时间新在前），附 anomaly 标记。"""
    by_sku: dict[str, dict] = {}
    for r in _read_all():
        cur = by_sku.get(r["sku"])
        if cur is None or r.get("logical_hours", 0) >= cur.get("logical_hours", 0):
            by_sku[r["sku"]] = r
    out = []
    for r in by_sku.values():
        row = dict(r)
        row["anomaly"] = _is_anomaly(row)
        out.append(row)
    out.sort(key=lambda r: r.get("ts", 0), reverse=True)
    return out


def history(sku: str) -> list[dict]:
    """单 sku 回流时间线（logical_hours 升序），附 anomaly 标记。"""
    rows = [dict(r) for r in _read_all() if r.get("sku") == sku]
    rows.sort(key=lambda r: r.get("logical_hours", 0))
    for r in rows:
        r["anomaly"] = _is_anomaly(r)
    return rows


def anomalies() -> list[dict]:
    """当前处于异常状态的 sku 快照（进化 Agent 的第三证据源）。"""
    return [r for r in latest() if r["anomaly"]]
