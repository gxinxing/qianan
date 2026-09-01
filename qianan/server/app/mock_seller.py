"""Mock 卖家后台：live listing 注册表 + 确定性指标模拟器（PRD v0.3 · Feature 2）。

上架动作的「平台侧」落点：
- mock 页面提交 → 登记 live listing（jsonl 持久化，重启不丢）
- 指标模拟器：以 sku 为确定性种子，按逻辑时钟推进产生曝光/点击/转化序列
  （环境变量 MOCK_TIME_SCALE，默认 60 → 1 真实分钟 = 1 逻辑小时，
  演示现场几分钟即可跑出「几天」的数据；路演可调到 600 加速异常出现）
- 标题质量差 → CTR 系统性偏负：为进化飞轮制造真实信号。
  质量分由规则计算（长度窗口/含品牌/词数/含规格数字），无 LLM，诚实可复算。
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import threading
import time
import uuid
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "mock_seller"
LISTINGS_FILE = DATA_DIR / "listings.jsonl"

TIME_SCALE = float(os.environ.get("MOCK_TIME_SCALE", "60"))  # 逻辑秒 / 真实秒

_LOCK = threading.Lock()

# 平台日均曝光基数（模拟量级，仅影响曲线形态）
_PLATFORM_DAILY_IMPRESSIONS = {
    "amazon": 900,
    "shopee": 1400,
    "aliexpress": 1100,
    "lazada": 1000,
    "tiktokshop": 1800,
}

MAX_IMAGE_LEN = 2048  # data URL 不入库，防止 jsonl 膨胀


# ---------- live listing 注册表 ----------

def _read_all() -> list[dict]:
    if not LISTINGS_FILE.exists():
        return []
    rows: list[dict] = []
    for line in LISTINGS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def create_listing(payload: dict) -> dict:
    """登记一条 live listing；title/brand/price 必填，sku 缺省自动生成。"""
    title = str(payload.get("title", "")).strip()
    brand = str(payload.get("brand", "")).strip()
    price = payload.get("price")
    if not title or not brand or price in (None, ""):
        raise ValueError("title / brand / price 为必填")
    image = str(payload.get("image", ""))
    if len(image) > MAX_IMAGE_LEN:
        image = ""  # data URL 不持久化，live 页显示占位图
    listing = {
        "listing_id": "ML-" + uuid.uuid4().hex[:8],
        "sku": str(payload.get("sku", "")).strip() or "SKU-" + uuid.uuid4().hex[:8].upper(),
        "platform": str(payload.get("platform", "amazon")),
        "title": title[:200],
        "brand": brand,
        "bullets": [str(b)[:500] for b in (payload.get("bullets") or []) if str(b).strip()][:5],
        "description": str(payload.get("description", "")),
        "price": float(price),
        "quantity": int(payload.get("quantity") or 0),
        "image": image,
        "published_at": time.time(),
        "source": "mock_seller_central",
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with open(LISTINGS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(listing, ensure_ascii=False) + "\n")
    return listing


def get_listing(listing_id: str) -> dict | None:
    return next((r for r in _read_all() if r.get("listing_id") == listing_id), None)


def find_by_sku(sku: str) -> dict | None:
    rows = [r for r in _read_all() if r.get("sku") == sku]
    return rows[-1] if rows else None


def list_listings() -> list[dict]:
    rows = _read_all()
    rows.sort(key=lambda r: r.get("published_at", 0), reverse=True)
    return rows


# ---------- 指标模拟器 ----------

def _seed(sku: str) -> int:
    return int(hashlib.md5(sku.encode("utf-8")).hexdigest()[:8], 16)


def _title_quality(title: str, brand: str) -> float:
    """标题质量分（0~1，规则计算）：长度窗口 / 含品牌 / 关键词丰富度 / 含规格数字。"""
    t = (title or "").strip()
    if not t:
        return 0.0
    score = 0.0
    n = len(t)
    if 60 <= n <= 170:
        score += 0.35
    elif 30 <= n < 60 or 170 < n <= 200:
        score += 0.15
    if brand and brand.lower() in t.lower():
        score += 0.25
    if len(re.findall(r"[A-Za-z0-9]+", t)) >= 8:
        score += 0.2
    if re.search(r"\d", t):
        score += 0.2
    return min(score, 1.0)


def metrics_series(listing: dict, now: float | None = None) -> dict:
    """按逻辑时钟生成逐小时序列（同一 sku 任意时刻重算结果一致，可复算）。"""
    now = now or time.time()
    published = float(listing.get("published_at", now))
    logical_elapsed_s = max(0.0, now - published) * TIME_SCALE
    hours = min(int(logical_elapsed_s // 3600), 24 * 30)  # 封顶 30 逻辑天
    platform = str(listing.get("platform", "amazon"))
    daily = _PLATFORM_DAILY_IMPRESSIONS.get(platform, 800)
    quality = _title_quality(listing.get("title", ""), listing.get("brand", ""))
    ctr = 0.028 * (0.4 + quality)  # 0.011 ~ 0.039：差标题跌破 0.02 异常基线
    cvr = 0.08 * (0.5 + 0.5 * quality)
    base = _seed(str(listing.get("sku") or listing.get("listing_id", "")))
    series: list[dict] = []
    clk_acc = 0.0  # 小数累加器：低 CTR 商品不被 int() 截断成恒 0（保持确定性）
    cnv_acc = 0.0
    for h in range(hours):
        rng = random.Random(base + h)
        wave = 1 + 0.3 * math.sin(h / 6)
        imp = int(daily / 24 * wave * rng.uniform(0.85, 1.15))
        clk_acc += imp * ctr * rng.uniform(0.8, 1.2)
        clk = int(clk_acc)
        clk_acc -= clk
        cnv_acc += clk * cvr * rng.uniform(0.7, 1.3)
        cnv = int(cnv_acc)
        cnv_acc -= cnv
        series.append(
            {
                "slot": h,
                "ts": published + (h + 1) * 3600 / TIME_SCALE,  # 映射回真实时间轴
                "impressions": imp,
                "clicks": clk,
                "conversions": cnv,
            }
        )
    totals = {
        "impressions": sum(s["impressions"] for s in series),
        "clicks": sum(s["clicks"] for s in series),
        "conversions": sum(s["conversions"] for s in series),
    }
    totals["ctr"] = round(totals["clicks"] / totals["impressions"], 4) if totals["impressions"] else 0.0
    return {
        "sku": listing.get("sku"),
        "listing_id": listing.get("listing_id"),
        "platform": platform,
        "published_at": published,
        "time_scale": TIME_SCALE,
        "logical_hours": hours,
        "title_quality": round(quality, 3),
        "series": series,
        "totals": totals,
    }
