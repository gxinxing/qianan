"""生成结果的文件仓库：任务完成后把上架包落盘，供文件管理区 / 后台管理消费。

目录结构：server/data/tasks/<task_id>/
  task.json   任务元信息（商品名/平台/状态/自愈次数/合规摘要）
  export.json 完整导出包（listing JSON + 各平台后台导入 CSV）
  images/     各平台主图（下载到本地，避免 OSS 签名 URL 过期）
"""
from __future__ import annotations

import json
import shutil
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from .import_files import build_import_files
from .paths import writable_dir
from .schemas import TaskRecord, TaskStatus

# 云函数等只读文件系统部署：用 paths.writable_dir 自动回退到 QIANAN_DATA_DIR
DATA_DIR = writable_dir("data", "tasks")
IMAGE_DIR_NAME = "images"


def _validate_download_url(url: str) -> None:
    """防止 SSRF：只允许 https:// 和 mock:// 图片地址。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "mock"):
        raise ValueError(f"不安全的图片 URL scheme: {parsed.scheme or '无'}（仅允许 https）")
    if parsed.hostname and any(
        parsed.hostname.startswith(p) for p in ("127.", "10.", "172.16.", "172.17.", "172.18.", "172.19.", "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.", "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.", "192.168.", "[::1]")
    ):
        raise ValueError(f"禁止访问内网图片地址: {parsed.hostname}")


def task_dir(task_id: str) -> Path:
    return DATA_DIR / task_id


def _meta(task: TaskRecord) -> dict:
    listings = task.listings or []
    return {
        "task_id": task.task_id,
        "product_name": task.request.product_name,
        "platforms": list(task.request.platforms),
        "status": task.status.value,
        "stage": task.stage,
        "error": task.error,
        "created_at": task.created_at,
        "done_at": time.time() if task.status == TaskStatus.done else None,
        "platforms_done": [
            {"platform": l.platform, "display_name": l.display_name, "passed": l.compliance_passed,
             "revised_count": l.revised_count, "images": len(l.images)}
            for l in listings
        ],
        "revised_total": sum(l.revised_count for l in listings),
        "compliance_passed_total": sum(1 for l in listings if l.compliance_passed),
    }


def persist_task(task: TaskRecord) -> None:
    """任务完成时落盘：task.json + export.json，图片异步下载。"""
    if task.status != TaskStatus.done:
        return
    d = task_dir(task.task_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "task.json").write_text(
        json.dumps(_meta(task), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    export = {
        "product_name": task.request.product_name,
        "understanding": task.understanding.model_dump() if task.understanding else None,
        "listings": [
            {**l.model_dump(), "import_files": build_import_files(task.request.product_name, l)}
            for l in (task.listings or [])
        ],
        "trace": [e.model_dump() for e in (task.trace or [])],
        "plan": task.plan.model_dump() if task.plan else None,
        "memory_recall": [m.model_dump() for m in (task.memory_recall or [])],
        "reflections": [r.model_dump() for r in (task.reflections or [])],
    }
    (d / "export.json").write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")
    for listing in task.listings or []:
        csv_map = build_import_files(task.request.product_name, listing)
        for name, content in csv_map.items():
            if content:
                (d / name).write_text(content, encoding="utf-8")
    threading.Thread(target=_download_images, args=(d, task), daemon=True).start()


def _download_images(d: Path, task: TaskRecord) -> None:
    img_dir = d / IMAGE_DIR_NAME
    img_dir.mkdir(exist_ok=True)
    for listing in task.listings or []:
        for idx, url in enumerate(listing.images or []):
            ext = Path(url.split("?")[0]).suffix or ".png"
            target = img_dir / f"{listing.platform}_{idx + 1}{ext}"
            if target.exists():
                continue
            try:
                _validate_download_url(url)
                req = urllib.request.Request(url, headers={"User-Agent": "qianan-file-store"})
                with urllib.request.urlopen(req, timeout=20) as r, open(target, "wb") as f:
                    shutil.copyfileobj(r, f)
            except Exception:  # noqa: BLE001 —— 图片下载失败不影响文件管理主流程
                target.unlink(missing_ok=True)


def _scan_package(d: Path) -> dict | None:
    meta_file = d / "task.json"
    if not meta_file.exists():
        return None
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    files: list[dict] = []
    for p in sorted(d.rglob("*")):
        if not p.is_file() or p.name == "task.json":
            continue
        rel = p.relative_to(d).as_posix()
        kind = "image" if IMAGE_DIR_NAME in rel else ("csv" if p.suffix == ".csv" else "json")
        files.append({"name": rel, "size": p.stat().st_size, "kind": kind})
    meta["files"] = files
    meta["total_size"] = sum(f["size"] for f in files)
    return meta


def list_packages() -> list[dict]:
    if not DATA_DIR.exists():
        return []
    packages = []
    for d in sorted(DATA_DIR.iterdir()):
        if d.is_dir():
            pkg = _scan_package(d)
            if pkg:
                packages.append(pkg)
    packages.sort(key=lambda p: p.get("done_at") or p.get("created_at") or 0, reverse=True)
    return packages


def get_package(task_id: str) -> dict | None:
    d = task_dir(task_id)
    if not d.exists():
        return None
    return _scan_package(d)


def delete_package(task_id: str) -> bool:
    d = task_dir(task_id)
    if not d.exists():
        return False
    shutil.rmtree(d, ignore_errors=True)
    return True


def resolve_file(task_id: str, rel: str) -> Path | None:
    """把包内相对路径解析为绝对路径；越界（路径穿越）返回 None。"""
    d = task_dir(task_id).resolve()
    target = (d / rel).resolve()
    if d not in target.parents:
        return None
    return target if target.is_file() else None
