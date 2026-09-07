"""长期记忆库：经验教训（experiences）+ 用户反馈（feedback），JSONL 持久化。

设计要点（对齐架构决策）：
- 网关无 embeddings → 用「平台/类目标签过滤 + 命中频次 + 时间」做结构化检索，
  确定性强、演示可复现；检索函数签名预留向量升级空间。
- 追加写 + 线程锁；读取容忍坏行。
- QIANAN_MEMORY=0 可一键关闭注入（应急开关）。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path

from .paths import writable_dir

DATA_DIR = writable_dir("data", "memory")
EXPERIENCE_FILE = DATA_DIR / "experiences.jsonl"
FEEDBACK_FILE = DATA_DIR / "feedback.jsonl"

_LOCK = threading.Lock()
MAX_LESSON_LEN = 40  # 注入提示词时单条上限，防干扰文案


def _enabled() -> bool:
    return os.getenv("QIANAN_MEMORY", "1") != "0"


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _append_jsonl(path: Path, row: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _rewrite_jsonl(path: Path, rows: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ---------- 经验教训 ----------

def remember(
    platform: str,
    category: str,
    lesson: str,
    source_task: str = "",
    check_id: str = "",
) -> dict:
    """把一条自愈/反思蒸馏出的教训写入记忆库。"""
    entry = {
        "id": uuid.uuid4().hex[:10],
        "platform": platform,
        "category": category,
        "lesson": lesson[:120],
        "check_id": check_id,
        "source_task": source_task,
        "hit_count": 0,
        "ts": time.time(),
    }
    _append_jsonl(EXPERIENCE_FILE, entry)
    return entry


def recall(platform: str = "", category: str = "", k: int = 3) -> list[dict]:
    """结构化检索 top-k 条教训：平台精确优先 → 命中频次 → 最近。"""
    if not _enabled():
        return []
    rows = _read_jsonl(EXPERIENCE_FILE)
    if platform:
        exact = [r for r in rows if r.get("platform") == platform]
        rows = exact or rows
    if category:
        cat = [r for r in rows if r.get("category") == category]
        if cat:
            rows = cat
    rows.sort(key=lambda r: (r.get("hit_count", 0), r.get("ts", 0)), reverse=True)
    return rows[:k]


def mark_hit(ids: list[str]) -> None:
    """注入命中后回写 hit_count，让高频教训排序更靠前。"""
    if not ids:
        return
    rows = _read_jsonl(EXPERIENCE_FILE)
    hit = set(ids)
    changed = False
    for r in rows:
        if r.get("id") in hit:
            r["hit_count"] = r.get("hit_count", 0) + 1
            changed = True
    if changed:
        _rewrite_jsonl(EXPERIENCE_FILE, rows)


def list_experiences(limit: int = 100) -> list[dict]:
    rows = _read_jsonl(EXPERIENCE_FILE)
    rows.sort(key=lambda r: r.get("ts", 0), reverse=True)
    return rows[:limit]


# ---------- 用户反馈 ----------

def add_feedback(task_id: str, platform: str, rating: int, comment: str = "") -> dict:
    entry = {
        "task_id": task_id,
        "platform": platform,
        "rating": rating,
        "comment": comment[:200],
        "ts": time.time(),
    }
    _append_jsonl(FEEDBACK_FILE, entry)
    return entry


def list_feedback(limit: int = 200) -> list[dict]:
    rows = _read_jsonl(FEEDBACK_FILE)
    rows.sort(key=lambda r: r.get("ts", 0), reverse=True)
    return rows[:limit]


def list_all() -> dict:
    return {
        "experiences": list_experiences(),
        "feedback": list_feedback(),
        "enabled": _enabled(),
    }


# ---------- SFT 训练对导出 ----------

def export_training_data() -> list[dict]:
    """把好评反馈整理成 SFT 训练对（微调暂不做，先把数据积累好）。

    每条 = {instruction, input, output, rating}，rating>0 视为正样本。
    真正的 listing 成品在 export.json，这里只保留反馈信号骨架。
    """
    out = []
    for fb in list_feedback():
        out.append(
            {
                "instruction": "为跨境平台上架文案打分与改进",
                "input": f"平台={fb.get('platform')} 任务={fb.get('task_id')}",
                "output": fb.get("comment", ""),
                "rating": fb.get("rating", 0),
            }
        )
    return out
