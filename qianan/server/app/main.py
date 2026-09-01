"""千岸 API 服务入口。

启动：cd server && uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from .agents.compliance import ComplianceAgent
from .agents import evolution
from .agents.ideation import IdeationAgent
from .bailian.client import get_client
from .economics import EconomicsInput, evaluate
from .file_store import (
    delete_package,
    get_package,
    list_packages,
    persist_task,
    resolve_file,
    task_dir,
)
from .import_files import build_import_files, sku_for
from .orchestrator import run_pipeline
from .publisher import runner as publish_runner
from .publisher import store as publish_store
from . import collector, extdata, memory_store, mock_seller, skill_store
from .rules_store import all_platforms, load_rules
from .schemas import (
    AuditRequest,
    Feedback,
    GenerateRequest,
    IdeationRequest,
    PlatformListing,
    PublishRequest,
    TaskRecord,
    TaskStatus,
)
from .task_store import create_task, delete_task, get_task, list_tasks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _client
    _client = get_client()
    skill_store.ensure_registered()  # 启动即按已安装清单重建工具注册表（连接器等启动后立即可用）
    logger.info("百炼客户端就绪（mock=%s）", _client.is_mock)
    yield


app = FastAPI(title="千岸 QianAn API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"chrome-extension://.*",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "mock": _client.is_mock if _client else None}


@app.get("/api/rules")
async def list_rules():
    """规则库透明页：返回 rules.v1 完整内容（结构化事实，规则引擎直接消费，非 LLM 生成）。"""
    return all_platforms()


@app.post("/api/economics")
async def economics(inp: EconomicsInput):
    """单位经济测算（确定性引擎）：每平台保本价/建议价/净利拆解与盈亏红牌。

    装了实时汇率连接器 → 用实时汇率（fx_source=live），否则内置 7.2 兜底。
    """
    fx, fx_source = await extdata.live_fx()
    try:
        return evaluate(inp, fx=fx, fx_source=fx_source)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"测算失败: {exc}") from exc


@app.post("/api/audit")
async def audit(req: AuditRequest):
    """表单草稿合规体检：直接跑规则引擎（与流水线第④步同源），供侧边栏/后台表单场景调用。"""
    try:
        rules = load_rules(req.platform)
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail=f"未知平台: {req.platform}") from None
    listing = PlatformListing(
        platform=req.platform,
        title=req.title,
        bullets=req.bullets,
        description=req.description,
        attributes=req.attributes,
        images=req.images,
    )
    ComplianceAgent().run(listing, rules, req.category)
    return {
        "platform": req.platform,
        "passed": listing.compliance_passed,
        "issues": [i.model_dump() for i in listing.compliance],
    }


@app.post("/api/ideation")
async def ideation(req: IdeationRequest):
    """选品灵感：市场 + 类目 → 3 条可一键上架的商品建议。

    装了趋势连接器 → 实时热搜注入选品 prompt（trend_source=live）；
    装了竞品连接器 → 顺带返回类目价格带。未装则静默降级，建议照常生成。
    """
    agent = IdeationAgent(_client)
    (trends, trend_source), (band, band_source) = await asyncio.gather(
        extdata.hot_keywords(req.market), extdata.competitor_band(req.category)
    )
    try:
        suggestions = await agent.run(req.market, req.category, trends=trends or None)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"选品建议生成失败: {exc}") from exc
    return {
        "market": req.market,
        "suggestions": suggestions,
        "trends": trends,
        "trend_source": trend_source,
        "competitor_band": band,
        "competitor_band_source": band_source,
    }


@app.get("/api/trends")
async def trends(market: str = "us"):
    """实时热搜词（轻量只读）：装了趋势连接器 = live，否则空列表（前端静默隐藏）。"""
    words, source = await extdata.hot_keywords(market)
    return {"market": market, "trends": words, "trend_source": source}


@app.post("/api/generate")
async def generate(req: GenerateRequest):
    task = create_task(req)
    asyncio.create_task(_run_and_persist(task))
    return {"task_id": task.task_id}


async def _run_and_persist(task: TaskRecord) -> None:
    """跑完流水线并把成品写入文件仓库（后台任务）。"""
    await run_pipeline(task, _client)
    if task.status == TaskStatus.done:
        try:
            persist_task(task)
        except Exception:  # noqa: BLE001 —— 落盘失败不影响主流程
            logger.exception("文件落盘失败")
        await _maybe_evolve()


async def _maybe_evolve() -> None:
    """每完成 3 个任务自动跑一轮进化分析（产出提案待人工审批）。"""
    done = sum(1 for t in list_tasks() if t.status == TaskStatus.done)
    if done and done % 3 == 0:
        try:
            result = await evolution.evolve(_client)
            logger.info("进化分析（自动）：%s", result)
        except Exception:  # noqa: BLE001
            logger.exception("进化分析失败（不影响主流程）")


@app.get("/api/tasks/{task_id}")
async def task_detail(task_id: str, request: Request):
    """任务详情（内存优先，重启后从文件仓库兜底还原）；已落盘的主图替换为本地 URL。"""
    task = get_task(task_id)
    if task is not None:
        data = task.model_dump()
    else:
        data = _task_from_disk(task_id)
        if data is None:
            raise HTTPException(status_code=404, detail="task not found")
    _localize_listing_images(task_id, data["listings"], str(request.base_url).rstrip("/"))
    return data


def _task_from_disk(task_id: str) -> dict | None:
    """后端重启后内存任务丢失：从 export.json 还原任务详情，结果页不断档。"""
    if get_package(task_id) is None:
        return None
    export_file = resolve_file(task_id, "export.json")
    if export_file is None:
        return None
    export = json.loads(export_file.read_text(encoding="utf-8"))
    return {
        "task_id": task_id,
        "status": "done",
        "stage": "完成",
        "progress": 1.0,
        "request": {"product_name": export.get("product_name", "")},
        "understanding": export.get("understanding"),
        "listings": export.get("listings", []),
        "trace": export.get("trace", []),
        "error": None,
        "created_at": 0,
    }


def _localize_listing_images(task_id: str, listings: list[dict], base: str) -> None:
    """把已落盘的主图 URL 换成本地文件地址（OSS 签名会过期，路演现场不能断图）。

    未落盘（下载线程还没跑完/下载失败）的保持原 URL，不影响首次浏览。
    """
    for listing in listings:
        images = listing.get("images") or []
        for idx, url in enumerate(images):
            if not url.startswith("http"):
                continue
            ext = Path(url.split("?")[0]).suffix or ".png"
            rel = f"images/{listing.get('platform', 'p')}_{idx + 1}{ext}"
            if resolve_file(task_id, rel):
                images[idx] = f"{base}/api/files/{task_id}/download/{rel}"


@app.get("/api/tasks/{task_id}/export")
async def export(task_id: str):
    """一键导出上架包：listing JSON + 各平台后台导入 CSV（Amazon flat file / Shopee 批量上传模板）。"""
    task = get_task(task_id)
    if task is not None:
        listings = []
        for listing in task.listings:
            item = listing.model_dump()
            item["import_files"] = build_import_files(task.request.product_name, listing)
            listings.append(item)
        return {
            "product_name": task.request.product_name,
            "understanding": task.understanding,
            "listings": listings,
        }
    export_file = resolve_file(task_id, "export.json")
    if export_file is None:
        raise HTTPException(status_code=404, detail="task not found")
    return json.loads(export_file.read_text(encoding="utf-8"))


# ---------- Mock 卖家后台（PRD v0.3：上架动作的平台侧落点） ----------

MOCK_PAGE = Path(__file__).resolve().parents[2] / "web" / "public" / "mock-seller-central.html"


@app.get("/mock/seller-central")
async def mock_seller_page():
    """mock 卖家后台页面（FastAPI 直接伺服，上架链路不依赖前端 dev server）。"""
    if not MOCK_PAGE.is_file():
        raise HTTPException(status_code=404, detail="mock page not found")
    return FileResponse(MOCK_PAGE, media_type="text/html")


@app.post("/mock/api/listings")
async def mock_create_listing(body: dict):
    """mock 页面提交 → 登记 live listing（分配 listing_id 与 live_url）。"""
    try:
        listing = mock_seller.create_listing(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "listing_id": listing["listing_id"],
        "sku": listing["sku"],
        "live_url": f"http://localhost:3000/mock-seller-central.html#live/{listing['listing_id']}",
        "listing": listing,
    }


@app.get("/mock/api/listings")
async def mock_listings():
    """全部 live listing（新在前）：数据看板与 collector 消费。"""
    return {"listings": mock_seller.list_listings()}


@app.get("/mock/api/listings/{listing_id}")
async def mock_listing_detail(listing_id: str):
    listing = mock_seller.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")
    return listing


@app.get("/mock/api/metrics")
async def mock_metrics(sku: str = "", listing_id: str = ""):
    """指标模拟器：确定性逐小时序列（逻辑时钟，MOCK_TIME_SCALE 加速）。"""
    listing = mock_seller.find_by_sku(sku) if sku else mock_seller.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")
    return mock_seller.metrics_series(listing)


# ---------- 上架执行（PRD v0.3 · Feature 1：审批闸口 + 执行器留痕） ----------

def _publish_snapshot(task_id: str, platform: str) -> dict:
    """从任务产物中抽出单平台上架快照（内存优先，磁盘兜底）；缺平台/合规未过 → 抛 422/404。"""
    task = get_task(task_id)
    if task is not None:
        listing = next((l for l in task.listings if l.platform == platform), None)
        product_name = task.request.product_name
    else:
        data = _task_from_disk(task_id)
        if data is None:
            raise HTTPException(status_code=404, detail="task not found")
        listing = next((l for l in data["listings"] if l.get("platform") == platform), None)
        product_name = data["request"].get("product_name", "")
    if listing is None:
        raise HTTPException(status_code=404, detail=f"任务未生成 {platform} 平台上架包")
    passed = listing.compliance_passed if isinstance(listing, PlatformListing) else listing.get("compliance_passed", True)
    if not passed:
        raise HTTPException(status_code=422, detail="该平台上架包合规未通过，禁止上架（先在结果页修复合规问题）")
    snap = listing.model_dump() if isinstance(listing, PlatformListing) else dict(listing)
    snap["sku"] = sku_for(product_name, platform)  # 与导出 CSV 同一 SKU：商品身份贯穿导出与上架
    return snap


@app.post("/api/publish")
async def publish(req: PublishRequest):
    """确认上架：approved 显式置真才放行（硬闸口，严禁无人值守上架）。

    校验通过 → 建 PublishJob → 后台跑执行器（Playwright 驱动 mock 后台，
    全程 steps[] + 截图留痕）→ 前端轮询 job 状态看留痕回放。
    """
    if not req.approved:
        raise HTTPException(status_code=422, detail="上架必须经用户显式确认（approved=true）")
    snapshot = _publish_snapshot(req.task_id, req.platform)
    job = publish_store.create_job(req.task_id, req.platform, "mock_browser", snapshot["sku"])
    asyncio.create_task(publish_runner.run_publish(job["job_id"], snapshot))
    return {"job": job}


@app.get("/api/publish/jobs")
async def publish_jobs(task_id: str = ""):
    """上架任务列表（新在前）；带 task_id 时只看该任务的上架记录。"""
    jobs = publish_store.list_jobs()
    if task_id:
        jobs = [j for j in jobs if j.get("task_id") == task_id]
    return {"jobs": jobs}


@app.get("/api/publish/jobs/{job_id}")
async def publish_job_detail(job_id: str):
    """job 详情：状态机 + steps[] 留痕（动作/细节/截图文件名）。"""
    job = publish_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.get("/api/publish/jobs/{job_id}/shots/{filename}")
async def publish_job_shot(job_id: str, filename: str):
    """留痕截图下载（防路径穿越：只允许裸文件名）。"""
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=422, detail="非法文件名")
    path = publish_store.job_dir(job_id) / "shots" / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="screenshot not found")
    return FileResponse(path, media_type="image/png")


# ---------- 指标回流（PRD v0.3 · Feature 3：数据飞轮回流段） ----------

@app.post("/api/metrics/collect")
async def metrics_collect():
    """手动触发一轮回流：全部 live listing 当前快照落 metrics.jsonl（幂等）。"""
    return {"collected": collector.collect_once()}


@app.get("/api/metrics")
async def metrics_overview():
    """经营数据总览：惰性回流一轮 → 每 sku 最新快照 + 异常标记 + 关联上架 job。"""
    collector.collect_once()
    job_by_sku: dict[str, dict] = {}
    for job in publish_store.list_jobs():
        sku = job.get("sku")
        if sku and sku not in job_by_sku:
            job_by_sku[sku] = job
    rows = []
    for row in collector.latest():
        job = job_by_sku.get(row["sku"]) or {}
        rows.append({**row, "task_id": job.get("task_id"), "job_id": job.get("job_id")})
    return {
        "listings": rows,
        "anomaly_count": sum(1 for r in rows if r["anomaly"]),
        "baseline": {"ctr": collector.CTR_ANOMALY_BASELINE, "min_impressions": collector.MIN_IMPRESSIONS_FOR_ANOMALY},
    }


@app.get("/api/metrics/{sku}")
async def metrics_history(sku: str):
    """单 sku 回流时间线（画 CTR/曝光曲线用）。"""
    rows = collector.history(sku)
    if not rows:
        raise HTTPException(status_code=404, detail="sku 无回流数据（尚未上架或未回流）")
    return {"sku": sku, "history": rows}


# ---------- 文件管理区 ----------

@app.get("/api/files")
async def files_list():
    """文件仓库：已完成任务的导出包列表（磁盘持久化，重启不丢）。"""
    return {"packages": list_packages()}


@app.get("/api/files/{task_id}")
async def files_detail(task_id: str):
    pkg = get_package(task_id)
    if pkg is None:
        raise HTTPException(status_code=404, detail="package not found")
    return pkg


@app.get("/api/files/{task_id}/download/{filename:path}")
async def files_download(task_id: str, filename: str):
    """下载包内文件（export.json / 平台 CSV / 主图）。"""
    path = resolve_file(task_id, filename)
    if path is None:
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path, filename=Path(filename).name)


@app.get("/api/files/{task_id}/zip")
async def files_zip(task_id: str):
    """整包下载：export.json + 各平台导入 CSV + 主图打成一个 zip。"""
    d = task_dir(task_id)
    if not d.is_dir():
        raise HTTPException(status_code=404, detail="package not found")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(d.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(d).as_posix())
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="qianan_{task_id}.zip"'},
    )


@app.delete("/api/files/{task_id}")
async def files_delete(task_id: str):
    """删除导出包（磁盘文件 + 内存任务记录）。"""
    delete_task(task_id)
    if not delete_package(task_id):
        raise HTTPException(status_code=404, detail="package not found")
    return {"ok": True, "task_id": task_id}


# ---------- 后台管理 ----------

def _merged_tasks() -> list[dict]:
    """内存任务 + 磁盘文件包合并（后端重启后任务列表不丢）。"""
    merged = [
        {
            "task_id": t.task_id,
            "product_name": t.request.product_name,
            "status": t.status.value,
            "stage": t.stage,
            "platforms": list(t.request.platforms),
            "created_at": t.created_at,
            "error": t.error,
            "listings": [
                {"passed": l.compliance_passed, "revised_count": l.revised_count, "images": len(l.images)}
                for l in t.listings
            ],
            "source": "memory",
        }
        for t in list_tasks()
    ]
    known = {t["task_id"] for t in merged}
    for pkg in list_packages():
        if pkg["task_id"] in known:
            continue
        merged.append(
            {
                "task_id": pkg["task_id"],
                "product_name": pkg["product_name"],
                "status": "done",
                "stage": "完成",
                "platforms": pkg["platforms"],
                "created_at": pkg.get("created_at", 0),
                "error": None,
                "listings": [
                    {"passed": p["passed"], "revised_count": p["revised_count"], "images": p["images"]}
                    for p in pkg.get("platforms_done", [])
                ],
                "source": "disk",
            }
        )
    return merged


@app.get("/api/admin/stats")
async def admin_stats():
    """后台概览：任务量/状态分布/平台分布/合规与自愈指标。"""
    merged = _merged_tasks()
    by_status = {"queued": 0, "running": 0, "done": 0, "failed": 0}
    by_platform: dict[str, int] = {}
    passed = 0
    listing_total = 0
    revised = 0
    images = 0
    for t in merged:
        by_status[t["status"]] = by_status.get(t["status"], 0) + 1
        for p in t["platforms"]:
            by_platform[p] = by_platform.get(p, 0) + 1
        for l in t["listings"]:
            listing_total += 1
            if l["passed"]:
                passed += 1
            revised += l["revised_count"]
            images += l["images"]
    return {
        "tasks": {"total": len(merged), **by_status},
        "platforms": by_platform,
        "compliance": {
            "passed": passed,
            "total": listing_total,
            "pass_rate": round(passed / listing_total, 3) if listing_total else 0,
        },
        "self_heal": {"revised_total": revised},
        "images": images,
        "packages_on_disk": len(list_packages()),
    }


@app.get("/api/admin/tasks")
async def admin_tasks(limit: int = 20):
    """后台任务列表（内存 + 磁盘，最近优先）。"""
    merged = _merged_tasks()
    merged.sort(key=lambda t: t["created_at"], reverse=True)
    return {
        "tasks": [
            {
                "task_id": t["task_id"],
                "product_name": t["product_name"],
                "status": t["status"],
                "stage": t["stage"],
                "platforms": t["platforms"],
                "created_at": t["created_at"],
                "revised_total": sum(l["revised_count"] for l in t["listings"]),
                "passed_total": sum(1 for l in t["listings"] if l["passed"]),
                "listing_total": len(t["listings"]),
                "error": t["error"],
                "source": t["source"],
            }
            for t in merged[:limit]
        ]
    }


# ---------- Agent 记忆与反馈 ----------

@app.post("/api/feedback")
async def submit_feedback(fb: Feedback):
    """人类反馈：对单平台上架包打分（1=好评 / -1=差评），喂给记忆库与进化分析。"""
    if fb.rating not in (1, -1):
        raise HTTPException(status_code=422, detail="rating 只能为 1 或 -1")
    entry = memory_store.add_feedback(fb.task_id, fb.platform, fb.rating, fb.comment)
    return {"ok": True, "entry": entry}


@app.get("/api/agent/training-data")
async def training_data():
    """SFT 训练对导出：赛期内不做真微调，先把反馈数据按训练格式积累。"""
    return {"pairs": memory_store.export_training_data()}


@app.get("/api/agent")
async def agent_overview():
    """/agent 页数据：记忆条目 + 反馈 + 已装技能 + 进化度量（自愈率随任务序的趋势）。"""
    merged = _merged_tasks()
    merged.sort(key=lambda t: t["created_at"] or 0)
    trend = []
    for t in merged:
        listings = t["listings"]
        if not listings:
            continue
        revised = sum(l["revised_count"] for l in listings)
        trend.append(
            {
                "task_id": t["task_id"],
                "product_name": t["product_name"],
                "heal_rate": round(revised / len(listings), 3),
                "revised": revised,
            }
        )
    return {
        "memory": memory_store.list_all(),
        "skills": skill_store.list_installed(),
        "proposals": {
            "pending": sum(1 for p in evolution.list_proposals() if p.get("status") == "pending"),
        },
        "metrics": {"tasks": len(merged), "heal_trend": trend},
    }


# ---------- Skill 商店（工具链自主扩展） ----------

@app.get("/api/skills")
async def skills_list():
    """已安装技能：规则补丁生效平台 + 动态注册的新工具。"""
    skill_store.ensure_registered()
    return {"skills": skill_store.list_installed()}


@app.get("/api/skills/registry")
async def skills_registry():
    """可用技能目录（本地注册表；生产形态为远端市场）。"""
    return {"registry": skill_store.list_registry()}


@app.post("/api/skills/install")
async def skills_install(body: dict):
    """从 file:// 或 https:// 拉取技能清单 → 白名单校验 → 落盘生效（规则 overlay + 工具注册）。"""
    source = str(body.get("source", "")).strip()
    if not source:
        raise HTTPException(status_code=422, detail="缺少 source")
    try:
        manifest = skill_store.fetch_manifest(source)
        installed = skill_store.install_manifest(manifest)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 —— 网络/解析失败统一 502
        raise HTTPException(status_code=502, detail=f"技能拉取失败: {exc}") from exc
    return {"ok": True, "skill": {"id": installed.get("id"), "name": installed.get("name")}}


@app.delete("/api/skills/{skill_id}")
async def skills_uninstall(skill_id: str):
    """卸载：删文件 + 注销工具 + 规则库缓存失效（规则还原为源）。"""
    if not skill_store.uninstall(skill_id):
        raise HTTPException(status_code=404, detail="技能未安装")
    return {"ok": True, "skill_id": skill_id}


# ---------- 进化 Agent（提案 → 人审 → 生效） ----------

@app.get("/api/agent/proposals")
async def proposals_list():
    """进化提案（新版本在前）：待审/已批准/已驳回/已回滚。"""
    return {"proposals": evolution.list_proposals()}


@app.post("/api/agent/evolve")
async def evolve_now():
    """手动触发一轮进化分析：读记忆+差评，产出提案待人工审批（不自动生效）。"""
    try:
        return {"result": await evolution.evolve(_client)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"进化分析失败: {exc}") from exc


@app.post("/api/agent/proposals/{pid}/approve")
async def proposal_approve(pid: str):
    """批准即应用：prompt 补丁写提示词新版本，规则补丁写 overlay（均可回滚）。"""
    ok, detail = evolution.approve(pid)
    if not ok:
        raise HTTPException(status_code=400, detail=detail)
    return {"ok": True, "detail": detail}


@app.post("/api/agent/proposals/{pid}/reject")
async def proposal_reject(pid: str):
    ok, detail = evolution.reject(pid)
    if not ok:
        raise HTTPException(status_code=400, detail=detail)
    return {"ok": True, "detail": detail}


@app.post("/api/agent/proposals/{pid}/rollback")
async def proposal_rollback(pid: str):
    """回滚已生效提案：提示词还原上一版本 / 规则补丁移除。"""
    ok, detail = evolution.rollback(pid)
    if not ok:
        raise HTTPException(status_code=400, detail=detail)
    return {"ok": True, "detail": detail}
