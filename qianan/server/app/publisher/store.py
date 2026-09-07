"""PublishJob 存取：data/publish/jobs.jsonl + 每 job 目录（截图等产物）。"""
from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

from ..paths import writable_dir
from ..schemas import PublishJob

DATA_DIR = writable_dir("data", "publish")
JOBS_FILE = DATA_DIR / "jobs.jsonl"

_LOCK = threading.Lock()


def _read_all() -> list[dict]:
    if not JOBS_FILE.exists():
        return []
    rows: list[dict] = []
    for line in JOBS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _write_all(rows: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with open(JOBS_FILE, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


def create_job(task_id: str, platform: str, executor: str, sku: str) -> dict:
    job = PublishJob(job_id="pub-" + uuid.uuid4().hex[:8], task_id=task_id, platform=platform, executor=executor, sku=sku)
    rows = _read_all()
    rows.append(job.model_dump(mode="json"))
    _write_all(rows)
    job_dir(job.job_id).mkdir(parents=True, exist_ok=True)
    return job.model_dump(mode="json")


def get_job(job_id: str) -> dict | None:
    return next((r for r in _read_all() if r.get("job_id") == job_id), None)


def save_job(job: dict) -> None:
    rows = _read_all()
    for i, r in enumerate(rows):
        if r.get("job_id") == job.get("job_id"):
            rows[i] = job
            break
    else:
        rows.append(job)
    _write_all(rows)


def list_jobs(limit: int = 50) -> list[dict]:
    rows = _read_all()
    rows.sort(key=lambda r: r.get("created_at", 0), reverse=True)
    return rows[:limit]


def job_dir(job_id: str) -> Path:
    return DATA_DIR / job_id
