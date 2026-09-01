"""提示词版本化：prompts/*.md 为运行时来源，history.jsonl 审计。

进化提案经人审批准后调 save() 写新版本；rollback() 还原上一版本（同样记为一版）。
文件缺失时回退内置 DEFAULTS，保证服务永远有提示词可用。
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[0] / "prompts"
HISTORY_FILE = PROMPTS_DIR / "history.jsonl"

DEFAULTS = {
    "copywriting_system": (
        "你是跨境电商多平台 Listing 文案专家，精通各平台规则与多语言本地化（非直译）。\n"
        "严格按要求输出 JSON，不要输出 markdown 代码块或多余文字。"
    ),
    "copywriting_revise_system": (
        "你是跨境电商多平台 Listing 文案专家，负责根据合规体检反馈修订文案。\n"
        "保持原文语言与卖点不变，只修复被点名的违规点：禁用词换成具体客观的表达，"
        "超长字段压缩到上限以内，其余内容原样保留。\n"
        "严格输出 JSON，不要输出 markdown 代码块或多余文字。"
    ),
}

_LOCK = threading.Lock()


def load(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return DEFAULTS.get(name, "")


def save(name: str, content: str, source: str = "manual") -> dict:
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    content = content.strip() + "\n"
    (PROMPTS_DIR / f"{name}.md").write_text(content, encoding="utf-8")
    entry = {
        "id": uuid.uuid4().hex[:10],
        "name": name,
        "ts": time.time(),
        "source": source,
        "content": content.strip(),
    }
    with _LOCK:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def history(name: str = "") -> list[dict]:
    """版本历史（新版本在前）；不传 name 返回全部。"""
    if not HISTORY_FILE.exists():
        return []
    rows: list[dict] = []
    for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not name or r.get("name") == name:
            rows.append(r)
    rows.sort(key=lambda r: r.get("ts", 0), reverse=True)
    return rows


def rollback(name: str) -> tuple[bool, str]:
    """还原到上一版本；只有初始版本时回到内置默认。"""
    rows = history(name)
    if not rows:
        return False, f"{name} 无版本历史，无需回滚"
    prev = rows[1]["content"] if len(rows) > 1 else DEFAULTS.get(name, "")
    save(name, prev, source="rollback")
    return True, f"{name} 已回滚到上一版本"
