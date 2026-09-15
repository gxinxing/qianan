"""千岸 API 服务入口。

启动：cd server && uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import FileResponse, Response

from . import auth as cbauth
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
    ALL_PLATFORMS,
    AuditRequest,
    BatchGenerateRequest,
    Feedback,
    GenerateRequest,
    IdeationRequest,
    PlatformListing,
    PublishRequest,
    TaskRecord,
    TaskStatus,
)
from . import task_store
from .task_store import create_task, delete_task, get_task, list_tasks

# 批量上新：batch_id → 元信息（租户隔离，结构与 task_store 同源）
BATCHES: dict[str, dict] = {}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_client = None


def _get_client_cached():
    """懒加载百炼客户端：uvicorn 走 lifespan 预热；SCF Event 路径无 lifespan，首次调用兜底。"""
    global _client
    if _client is None:
        _client = get_client()
        skill_store.ensure_registered()  # 按已安装清单重建工具注册表（连接器等启动后立即可用）
        logger.info("百炼客户端就绪（mock=%s）", _client.is_mock)
    return _client


@asynccontextmanager
async def lifespan(app: FastAPI):
    _get_client_cached()
    yield


app = FastAPI(title="千岸 QianAn API", version="0.1.0", lifespan=lifespan)

# CORS 注意：CloudBase 网关本身已注入 CORS 头，后端不再重复添加，
# 否则浏览器收到两个 Access-Control-Allow-Origin 值会拒绝请求。
# 本地开发（无网关）需要 CORS 时设 QIANAN_ENABLE_CORS=1。
_ENABLE_CORS = os.getenv("QIANAN_ENABLE_CORS", "0") not in ("0", "false", "")
if _ENABLE_CORS:
    _BASE_ORIGINS = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://ai-native-d5gfb0dm2a28d1fe9-1419921079.tcloudbaseapp.com",
    ]
    _EXTRA_ORIGINS = [o.strip() for o in os.getenv("QIANAN_CORS_ORIGINS", "").split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_BASE_ORIGINS + _EXTRA_ORIGINS,
        allow_origin_regex=r"https://[a-z0-9-]+\.(tcloudbaseapp\.com|tcloudbase\.com|cloudbase\.net|app\.tcloudbase\.com)",
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
        max_age=86400,
    )


def _client_for_request():
    """按当前请求选客户端：只要本次请求带了 BYOK，就为它单独构造真实客户端。

    为什么不能直接复用 _get_client_cached()（进程级单例）：
      1. 服务端未预置 Key 时，单例是 MockBailianClient —— 复用它会导致访客填了
         Key 却仍拿到 mock 数据（静默失效，最坑）；
      2. 服务端 Key 存在但已失效/欠费时，单例是挂在无效 Key 上的真实客户端，
         且首次调用后会被 _ResilientClient 降级成 mock —— 复用它同样吃掉 BYOK。

    所以判定条件不能是「缓存是不是 mock」，而是「本请求有没有带 BYOK」。
    get_client() 内部按 ContextVar 取值，因此这里每次新建都能拿到访客自己的 Key。
    构造开销可忽略（只做一次非空检查），且不写回 _client，不污染其他请求。
    """
    from .bailian.client import has_byok
    if has_byok():
        return get_client()
    return _get_client_cached()


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "mock": _get_client_cached().is_mock,
        "auth": {
            "ready": cbauth.auth_ready(),
            "require_auth": cbauth.REQUIRE_AUTH,
        },
    }


@app.get("/api/me")
async def me(user: dict = Depends(cbauth.current_user)):
    """当前身份。uid 来自自包含 JWT，前端改不了 —— 多租户的信任根。"""
    return {
        "uid": cbauth.uid_of(user),
        "name": user.get("name") or "",
        "username": user.get("username") or "",
        "authenticated": bool(user.get("authenticated")),
        "tenancy": "self-jwt",
    }


class AuthCredentials(BaseModel):
    username: str
    password: str


def _auth_response(u: dict) -> dict:
    token = cbauth.issue_token(u["uid"], u["username"])
    return {
        "token": token,
        "uid": u["uid"],
        "username": u["username"],
        # 兼容前端 AuthProvider.toUser(session.session.user)
        "session": {"user": {"id": u["uid"], "username": u["username"], "name": u["username"]}},
    }


@app.post("/api/auth/register")
async def api_register(body: AuthCredentials):
    """注册新租户（自包含账号存储）。"""
    try:
        u = cbauth.create_user(body.username, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _auth_response(u)


@app.post("/api/auth/login")
async def api_login(body: AuthCredentials):
    """登录已注册租户，返回 JWT。"""
    u = cbauth.authenticate(body.username, body.password)
    if not u:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return _auth_response(u)


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


# ---------- 评测集（Evals：合规规则与历史事故的回归测试） ----------

from .paths import readonly_dir  # noqa: E402
EVALS_REPORT = readonly_dir("data", "evals") / "report.json"

_EMPTY_EVALS_REPORT = {
    "generated_at": None,
    "total": 0,
    "passed": 0,
    "failed": 0,
    "skipped": 0,
    "duration_ms": 0,
    "suites": [],
}


@app.get("/api/evals")
async def evals_report():
    """最新评测报告快照；报告未生成时返回空结构（前端展示空态，不 404）。"""
    if not EVALS_REPORT.is_file():
        return dict(_EMPTY_EVALS_REPORT)
    return json.loads(EVALS_REPORT.read_text(encoding="utf-8"))


@app.post("/api/evals/run")
async def evals_run(user: dict = Depends(cbauth.require_user)):
    """跑一轮评测（python -m evals.run），返回新生成的报告内容。"""
    cwd = Path(__file__).resolve().parents[1]
    try:
        proc = await asyncio.create_subprocess_exec(
            "/usr/bin/python3",
            "-m",
            "evals.run",
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    except asyncio.TimeoutError as exc:
        proc.kill()
        raise HTTPException(status_code=500, detail="评测运行超时（>120s）") from exc
    if proc.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"评测运行失败(exit={proc.returncode}): {stderr.decode('utf-8', 'replace')[-2000:]}",
        )
    if not EVALS_REPORT.is_file():
        raise HTTPException(status_code=500, detail="评测运行完成但未产出 report.json")
    return json.loads(EVALS_REPORT.read_text(encoding="utf-8"))


@app.post("/api/ideation")
async def ideation(req: IdeationRequest):
    """选品灵感：市场 + 类目 → 3 条可一键上架的商品建议。

    装了趋势连接器 → 实时热搜注入选品 prompt（trend_source=live）；
    装了竞品连接器 → 顺带返回类目价格带。未装则静默降级，建议照常生成。
    """
    agent = IdeationAgent(_get_client_cached())
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
async def generate(req: GenerateRequest, request: Request, user: dict = Depends(cbauth.require_user)):
    cbauth.check_rate_limit(cbauth.client_ip(request))
    # 浏览器上传的 base64 图 → 先上公网临时图床 → 交给 AI 网关以 URL 消费
    # （聚合网关图片任务拒绝超大 data URL body：nginx 413；localhost URL 网关又无法回访）
    if req.image_base64 and not req.image_url:
        import base64 as _b64

        from . import uploader

        try:
            raw = req.image_base64.split(",", 1)[-1]
            data = _b64.b64decode(raw)
            req.image_url = uploader.upload_bytes(data)
            logger.info("商品图已上传公网图床: %s", req.image_url[:80])
        except Exception as exc:  # noqa: BLE001 —— 上传失败保留 base64，VL/视觉路径自行容错
            logger.warning("商品图上传公网失败，回退 base64 直传: %s", exc)
    task = create_task(req, owner_uid=cbauth.uid_of(user))
    logger.info("任务 %s 归属租户 %s", task.task_id, task.owner_uid)
    # 云函数环境：同步跑完 pipeline 后返回完整结果（SCF 无后台进程）
    if os.getenv("TENCENT_SCF"):
        from app.orchestrator import run_pipeline
        from app.file_store import persist_task
        await run_pipeline(task, get_client())
        if task.status == TaskStatus.done:
            try:
                persist_task(task)
            except Exception:  # noqa: BLE001
                logger.exception("SCF persist task failed")
        return task.model_dump()
    # 正常模式：异步后台跑
    asyncio.create_task(_run_and_persist(task))
    return {"task_id": task.task_id}


@app.post("/api/generate/batch")
async def generate_batch(req: BatchGenerateRequest, request: Request, user: dict = Depends(cbauth.require_user)):
    """批量上新：一次提交多个商品，逐一对齐各平台生成合规 Listing。

    赛事场景一「批量完成 Listing 撰写与后台上架」评分点。
    复用与单任务完全相同的 create_task + run_pipeline，仅在外层做多商品编排。
    - 正常模式：并发起后台任务，立即返回 batch_id + task_ids（前端轮询各 task）。
    - SCF 模式：同步顺序跑完每个 task 后返回完整结果（保证线上也能跑通）。
    """
    cbauth.check_rate_limit(cbauth.client_ip(request))
    if not req.items:
        raise HTTPException(status_code=422, detail="items 不能为空")
    owner = cbauth.uid_of(user)
    tasks: list[TaskRecord] = []
    for item in req.items:
        # 浏览器上传的 base64 图 → 公网临时图床（与单任务同逻辑）
        if item.image_base64 and not item.image_url:
            import base64 as _b64

            from . import uploader

            try:
                raw = item.image_base64.split(",", 1)[-1]
                data = _b64.b64decode(raw)
                item.image_url = uploader.upload_bytes(data)
            except Exception as exc:  # noqa: BLE001
                logger.warning("批量商品图上传失败，回退 base64 直传: %s", exc)
        if req.platforms:
            item.platforms = [p for p in req.platforms if p in ALL_PLATFORMS] or list(ALL_PLATFORMS)
        tasks.append(create_task(item, owner_uid=owner))

    batch_id = f"batch_{uuid.uuid4().hex[:12]}"
    BATCHES[batch_id] = {
        "batch_id": batch_id,
        "owner_uid": owner,
        "task_ids": [t.task_id for t in tasks],
        "created_at": int(asyncio.get_event_loop().time()),
    }

    if os.getenv("TENCENT_SCF"):
        from .file_store import persist_task

        for t in tasks:
            await run_pipeline(t, get_client())
            if t.status == TaskStatus.done:
                try:
                    persist_task(t)
                except Exception:  # noqa: BLE001
                    logger.exception("SCF 批量 persist 失败")
        return {"batch_id": batch_id, "tasks": [t.model_dump() for t in tasks]}

    for t in tasks:
        asyncio.create_task(_run_and_persist(t))
    return {"batch_id": batch_id, "task_ids": [t.task_id for t in tasks]}


@app.get("/api/batch/{batch_id}")
async def batch_status(batch_id: str, request: Request, user: dict = Depends(cbauth.current_user)):
    """批量进度汇总：返回该 batch 下每个 task 的状态/进度，供前端批量页轮询。"""
    batch = BATCHES.get(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="batch 不存在")
    owner = cbauth.uid_of(user) if user else None
    if owner and batch.get("owner_uid") and batch["owner_uid"] != owner:
        raise HTTPException(status_code=403, detail="无权限访问该 batch")
    items = []
    for tid in batch["task_ids"]:
        t = get_task(tid)
        if t is None:
            items.append({"task_id": tid, "status": "missing"})
            continue
        req = t.request
        items.append(
            {
                "task_id": t.task_id,
                "status": t.status,
                "stage": t.stage,
                "progress": t.progress,
                "product_name": getattr(req, "product_name", "") if req else "",
                "platforms": getattr(req, "platforms", []) if req else [],
            }
        )
    done = sum(1 for i in items if i["status"] == "done")
    return {
        "batch_id": batch_id,
        "total": len(items),
        "done": done,
        "running": sum(1 for i in items if i["status"] == "running"),
        "failed": sum(1 for i in items if i["status"] == "failed"),
        "items": items,
    }


async def _run_and_persist(task: TaskRecord) -> None:
    """跑完流水线并把成品写入文件仓库（后台任务）。"""
    await run_pipeline(task, _get_client_cached())
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
            result = await evolution.evolve(_get_client_cached())
            logger.info("进化分析（自动）：%s", result)
        except Exception:  # noqa: BLE001
            logger.exception("进化分析失败（不影响主流程）")


# =====================================================================
# 对话式 SSE 接口：Agent 自主编排（function calling tool loop）
# =====================================================================

from fastapi.responses import StreamingResponse  # noqa: E402
from .agent_core.trace import set_event_hook  # noqa: E402
from .chat_agent import run_chat_agent  # noqa: E402


class ChatRequest(BaseModel):
    """对话式生成请求：自然语言描述 + 可选图片。"""

    message: str = ""
    product_name: str = ""
    selling_points: str = ""
    category: str = "home_kitchen"
    image_url: str | None = None
    image_base64: str | None = None
    platforms: list[str] = None  # None = 全 5 平台
    ablation: dict | None = None


def _sse_line(data: dict) -> bytes:
    """把 dict 编码为 SSE data: 行。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


def _listing_snapshot(task: TaskRecord) -> dict:
    """提取当前 task 的 listing 产物快照（供前端右侧面板渲染）。

    type 必须是 `listing_full`：前端 `useChat.ts` 先无条件匹配 `type === "listing"`
    并当作「单个平台产物」处理，全量快照若也叫 listing，会被包装成一条
    `platform: undefined` 的假记录，**覆盖掉右侧已生成的多个平台产物**，
    还会把 status 硬编码成 running、plan 清空成 null。
    """
    return {
        "type": "listing_full",
        # 必须是 .value：str(TaskStatus.done) 在 Python 3.10 得到 "TaskStatus.done"，
        # 前端 `status === "done"` 永远判不中。
        "status": task.status.value,
        "stage": task.stage,
        "progress": task.progress,
        "plan": task.plan.model_dump() if task.plan else None,
        "memory_recall": [m.model_dump() for m in task.memory_recall],
        "reflections": [r.model_dump() for r in task.reflections],
        "listings": [
            {
                "platform": l.platform,
                "display_name": l.display_name,
                "title": l.title,
                "bullets": l.bullets,
                "description": l.description[:200] if l.description else "",
                "images": l.images[:3] if l.images else [],
                "detail_images": (l.detail_images or [])[:4],
                "video_url": l.video_url,
                "compliance_passed": l.compliance_passed,
                "revised_count": l.revised_count,
                "compliance_errors": sum(1 for i in l.compliance if i.severity == "error"),
                "compliance_warns": sum(1 for i in l.compliance if i.severity == "warn"),
            }
            for l in task.listings
        ],
    }


#: 被用户取消的对话任务 id。仅用于「停止后别再烧额度」，
#: 进程内集合足够（SSE 断开即无消费者，跨进程恢复不在本层范围）。
_CHAT_CANCELLED: set[str] = set()


@app.post("/api/chat/{task_id}/cancel")
async def chat_cancel(task_id: str):
    """真正停止后台 Agent。

    此前「停止」只断开前端 fetch —— SSE 关闭了，但后台 `run_chat_agent`
    仍在跑工具循环，继续消耗模型额度。这里置位后，工具循环会在下一个检查点退出。
    """
    existed = task_id in _CHAT_CANCELLED
    _CHAT_CANCELLED.add(task_id)
    logger.info("chat 任务 %s 收到取消指令", task_id)
    return {"ok": True, "task_id": task_id, "cancelled": True, "was_running": not existed}


@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request, user: dict = Depends(cbauth.require_user)):
    # 限流：chat 是公开可访问的对话入口，一次请求会触发多轮模型调用与出图，
    # 没有限流的话一个公开地址被反复调用就能把模型额度烧完。与 /api/generate 同策略。
    cbauth.check_rate_limit(cbauth.client_ip(request))

    # BYOK：访客可在前端填自己的百炼 Key，随请求头带来，本次调用走他自己的额度。
    # 服务端预置额度耗尽或未配置时，这是让外部评审仍能真实跑通的唯一途径。
    from .bailian.client import has_byok, set_request_keys
    set_request_keys(
        api_key=request.headers.get("x-bailian-api-key"),
        dashscope_key=request.headers.get("x-dashscope-api-key"),
    )
    if has_byok():
        logger.info("本次请求使用 BYOK（访客自带 Key）")

    """对话式 Agent 接口：Agent 用 function calling 自主编排上架全流程。

    与旧版（跑固定 pipeline）不同，新版让模型在对话中自主决定：
    理解商品 → 生成文案 → 审核 → 发现问题自己改 → 出图 → 出视频 → 交付。
    全程通过 SSE 事件实时推送"我在做 X"和中间产物。

    事件类型:
      - init:         {type, task_id}
      - text:         {type, content}          — Agent 的文本回复
      - trace:        {type, phase, tool, args, result, status}  — 工具调用追踪
      - listing:      {type, platform, title, ...} — 单个平台的产物更新
      - listing_full: {type, status, stage, progress, listings[]} — 全量快照
      - done:         {type, task_id, status, summary}
      - error:        {type, message}
    """
    from .schemas import ALL_PLATFORMS, AblationConfig, GenerateRequest

    platforms = req.platforms or list(ALL_PLATFORMS)
    abl = AblationConfig(**req.ablation) if req.ablation else None

    product_name = req.product_name or req.message[:200]
    selling_points = req.selling_points or req.message

    gen_req = GenerateRequest(
        product_name=product_name,
        selling_points=selling_points,
        category=req.category,
        image_url=req.image_url,
        image_base64=req.image_base64,
        platforms=platforms,
        ablation=abl,
    )

    # 图片上传
    if gen_req.image_base64 and not gen_req.image_url:
        import base64 as _b64
        from . import uploader
        try:
            raw = gen_req.image_base64.split(",", 1)[-1]
            data = _b64.b64decode(raw)
            gen_req.image_url = uploader.upload_bytes(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("chat 图片上传失败: %s", exc)

    # 与 /api/generate 一致地归属租户：游客也会拿到基于 IP+UA 派生的独立 uid。
    # 此前写死 "anonymous" 意味着所有访客的任务混在同一个租户下，互相可见。
    owner = cbauth.uid_of(user)
    task = create_task(gen_req, owner_uid=owner)
    logger.info("chat 任务 %s 归属租户 %s", task.task_id, owner)
    _CHAT_CANCELLED.discard(task.task_id)  # 防御：task_id 复用时不要继承取消态
    client = _client_for_request()

    async def event_stream():
        """SSE 流：Agent 对话事件 + trace 事件合并推送。"""
        queue: asyncio.Queue = asyncio.Queue()

        # init
        await queue.put(_sse_line({"type": "init", "task_id": task.task_id}))

        # trace 事件钩子
        def trace_hook(event_data: dict):
            queue.put_nowait(_sse_line({"type": "trace", **event_data}))

        set_event_hook(task.task_id, trace_hook)

        # chat agent 事件回调
        pushed_done = False

        def chat_event(evt_type: str, content):
            nonlocal pushed_done
            if evt_type == "text":
                queue.put_nowait(_sse_line({"type": "text", "content": content}))
            elif evt_type == "listing":
                # 单平台产物更新。事件名统一为 `listing_update` —— 此前外层写死 "listing"，
                # 会把 payload 自带的 type 覆盖掉，前端只能靠 data.listings 是否存在来猜，
                # 全量快照（listing_full）也因此被误判成单平台事件、冲掉已生成的产物。
                payload = content if isinstance(content, dict) else {"data": str(content)}
                payload = {**payload, "type": "listing_update"}
                queue.put_nowait(_sse_line(payload))
            elif evt_type == "done":
                pushed_done = True
                queue.put_nowait(_sse_line({"type": "done", "task_id": task.task_id, "status": task.status.value, "summary": content}))
            elif evt_type == "error":
                queue.put_nowait(_sse_line({"type": "error", "message": content}))

        # 在后台跑 Agent（带上取消信号，停止时不再继续烧额度）
        def should_stop() -> bool:
            return task.task_id in _CHAT_CANCELLED

        agent_task = asyncio.create_task(
            run_chat_agent(task, client, req.message, on_event=chat_event, should_stop=should_stop)
        )

        # 推送循环
        last_snapshot = 0.0
        while not agent_task.done():
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=1.0)
                yield evt
                # 定期推送全量快照
                now = asyncio.get_event_loop().time()
                if now - last_snapshot > 3.0:
                    yield _sse_line(_listing_snapshot(task))
                    last_snapshot = now
            except asyncio.TimeoutError:
                now = asyncio.get_event_loop().time()
                if now - last_snapshot > 3.0:
                    yield _sse_line(_listing_snapshot(task))
                    last_snapshot = now

        # 排空队列
        while not queue.empty():
            yield queue.get_nowait()

        # 最终快照
        yield _sse_line(_listing_snapshot(task))

        if task.status == TaskStatus.failed:
            yield _sse_line({"type": "error", "message": task.error or "agent failed"})

        # 兜底 done：只在 Agent 自己没推过时补一个。
        # 此前无条件推送 → 前端总是收到两个 done，第二个还没有 summary，会把第一个覆盖掉。
        if not pushed_done:
            yield _sse_line({
                "type": "done",
                "task_id": task.task_id,
                "status": task.status.value,
                "summary": task.stage or "",
            })

        # 持久化：done 之外的 partial / cancelled 也必须落盘。
        # partial 意味着「跑出了一部分但没达标」，正是最需要留档以便续跑/复盘的状态；
        # 此前只存 done，这类任务一断线就彻底丢失。
        if task.status in (TaskStatus.done, TaskStatus.partial, TaskStatus.cancelled):
            try:
                persist_task(task)
            except Exception:  # noqa: BLE001
                logger.exception("chat persist task failed")

        set_event_hook(task.task_id, None)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/tasks/{task_id}")
async def task_detail(task_id: str, request: Request, user: dict = Depends(cbauth.current_user)):
    """任务详情（内存优先，重启后从文件仓库兜底还原）；已落盘的主图替换为本地 URL。"""
    if not task_store.visible_to(task_id, cbauth.uid_of(user)):
        raise HTTPException(status_code=404, detail="task not found")
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
        "plan": export.get("plan"),
        "memory_recall": export.get("memory_recall", []),
        "reflections": export.get("reflections", []),
        "error": None,
        "created_at": 0,
    }


def _localize_listing_images(task_id: str, listings: list[dict], base: str) -> None:
    """把已落盘的主图/详情图/视频 URL 换成本地文件地址（OSS 签名会过期，路演现场不能断图）。

    未落盘（下载线程还没跑完/下载失败）的保持原 URL，不影响首次浏览。
    """
    for listing in listings:
        # 主图
        images = listing.get("images") or []
        for idx, url in enumerate(images):
            if not isinstance(url, str) or not url.startswith("http"):
                continue
            ext = Path(url.split("?")[0]).suffix or ".png"
            rel = f"images/{listing.get('platform', 'p')}_{idx + 1}{ext}"
            if resolve_file(task_id, rel):
                images[idx] = f"{base}/api/files/{task_id}/download/{rel}"
        # 详情图
        detail_imgs = listing.get("detail_images") or []
        for idx, url in enumerate(detail_imgs):
            if not isinstance(url, str) or not url.startswith("http"):
                continue
            ext = Path(url.split("?")[0]).suffix or ".png"
            rel = f"images/{listing.get('platform', 'p')}_detail_{idx + 1}{ext}"
            if resolve_file(task_id, rel):
                detail_imgs[idx] = f"{base}/api/files/{task_id}/download/{rel}"
        # 视频
        video = listing.get("video_url")
        if isinstance(video, str) and video.startswith("http"):
            ext = Path(video.split("?")[0]).suffix or ".mp4"
            rel = f"images/{listing.get('platform', 'p')}_video{ext}"
            if resolve_file(task_id, rel):
                listing["video_url"] = f"{base}/api/files/{task_id}/download/{rel}"


@app.get("/api/tasks/{task_id}/export")
async def export(task_id: str, user: dict = Depends(cbauth.current_user)):
    """一键导出上架包：listing JSON + 各平台后台导入 CSV（Amazon flat file / Shopee 批量上传模板）。"""
    if not task_store.visible_to(task_id, cbauth.uid_of(user)):
        raise HTTPException(status_code=404, detail="task not found")
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
async def publish(req: PublishRequest, user: dict = Depends(cbauth.require_user)):
    """确认上架：approved 显式置真才放行（硬闸口，严禁无人值守上架）。

    校验通过 → 建 PublishJob → 后台跑执行器（Playwright 驱动 mock 后台，
    全程 steps[] + 截图留痕）→ 前端轮询 job 状态看留痕回放。
    """
    if not req.approved:
        raise HTTPException(status_code=422, detail="上架必须经用户显式确认（approved=true）")
    if not task_store.visible_to(req.task_id, cbauth.uid_of(user)):
        raise HTTPException(status_code=404, detail="task not found")
    snapshot = _publish_snapshot(req.task_id, req.platform)
    job = publish_store.create_job(req.task_id, req.platform, "mock_browser", snapshot["sku"])
    asyncio.create_task(publish_runner.run_publish(job["job_id"], snapshot))
    return {"job": job}


@app.get("/api/publish/jobs")
async def publish_jobs(task_id: str = "", user: dict = Depends(cbauth.require_user)):
    """上架任务列表（新在前）；带 task_id 时只看该任务的上架记录。"""
    jobs = publish_store.list_jobs()
    if task_id:
        jobs = [j for j in jobs if j.get("task_id") == task_id]
    return {"jobs": jobs}


@app.get("/api/publish/jobs/{job_id}")
async def publish_job_detail(job_id: str, user: dict = Depends(cbauth.require_user)):
    """job 详情：状态机 + steps[] 留痕（动作/细节/截图文件名）。"""
    job = publish_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.get("/api/publish/jobs/{job_id}/shots/{filename}")
async def publish_job_shot(job_id: str, filename: str):
    """留痕截图下载（防路径穿越：URL 解码后仍只允许裸文件名/裸 job_id，且拒绝反斜杠）。"""
    name = unquote(filename)
    if "/" in name or "\\" in name or ".." in name or "\x00" in name:
        raise HTTPException(status_code=422, detail="非法文件名")
    jid = unquote(job_id)
    if "/" in jid or "\\" in jid or ".." in jid or "\x00" in jid:
        raise HTTPException(status_code=422, detail="非法 job_id")
    path = publish_store.job_dir(jid) / "shots" / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="screenshot not found")
    return FileResponse(path, media_type="image/png")


# ---------- 指标回流（PRD v0.3 · Feature 3：数据飞轮回流段） ----------

@app.post("/api/metrics/collect")
async def metrics_collect(user: dict = Depends(cbauth.require_user)):
    """手动触发一轮回流：全部 live listing 当前快照落 metrics.jsonl（幂等）。"""
    return {"collected": collector.collect_once()}


@app.get("/api/metrics")
async def metrics_overview(user: dict = Depends(cbauth.require_user)):
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
async def metrics_history(sku: str, user: dict = Depends(cbauth.require_user)):
    """单 sku 回流时间线（画 CTR/曝光曲线用）。"""
    rows = collector.history(sku)
    if not rows:
        raise HTTPException(status_code=404, detail="sku 无回流数据（尚未上架或未回流）")
    return {"sku": sku, "history": rows}


# ---------- 文件管理区 ----------

@app.get("/api/files")
async def files_list(user: dict = Depends(cbauth.current_user)):
    """文件仓库：当前租户可见的导出包列表（磁盘持久化，重启不丢）。"""
    uid = cbauth.uid_of(user)
    packages = [p for p in list_packages() if task_store.visible_to(str(p.get("task_id", "")), uid)]
    return {"packages": packages, "uid": uid}


@app.get("/api/files/{task_id}")
async def files_detail(task_id: str, user: dict = Depends(cbauth.current_user)):
    if not task_store.visible_to(task_id, cbauth.uid_of(user)):
        raise HTTPException(status_code=404, detail="package not found")
    pkg = get_package(task_id)
    if pkg is None:
        raise HTTPException(status_code=404, detail="package not found")
    return pkg


@app.get("/api/files/{task_id}/download/{filename:path}")
async def files_download(task_id: str, filename: str, user: dict = Depends(cbauth.current_user)):
    """下载包内文件（export.json / 平台 CSV / 主图）。

    <img> / <a download> 带不了 Authorization，支持 ?access_token= 兜底。
    """
    if not task_store.visible_to(task_id, cbauth.uid_of(user)):
        raise HTTPException(status_code=404, detail="file not found")
    path = resolve_file(task_id, filename)
    if path is None:
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path, filename=Path(filename).name)


@app.get("/api/files/{task_id}/zip")
async def files_zip(task_id: str, user: dict = Depends(cbauth.current_user)):
    """整包下载：export.json + 各平台导入 CSV + 主图打成一个 zip。"""
    if not task_store.visible_to(task_id, cbauth.uid_of(user)):
        raise HTTPException(status_code=404, detail="package not found")
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
async def files_delete(task_id: str, user: dict = Depends(cbauth.require_user)):
    """删除导出包（磁盘文件 + 内存任务记录）。"""
    delete_task(task_id)
    if not delete_package(task_id):
        raise HTTPException(status_code=404, detail="package not found")
    return {"ok": True, "task_id": task_id}


# ---------- 后台管理 ----------

def _merged_tasks(uid: str = "") -> list[dict]:
    """内存任务 + 磁盘文件包合并（后端重启后任务列表不丢），按租户过滤。"""
    merged = [
        {
            "task_id": t.task_id,
            "product_name": t.request.product_name,
            "status": t.status.value,
            "stage": t.stage,
            "platforms": list(t.request.platforms),
            "created_at": t.created_at,
            "error": t.error,
            "owner_uid": t.owner_uid,
            "listings": [
                {"passed": l.compliance_passed, "revised_count": l.revised_count, "images": len(l.images)}
                for l in t.listings
            ],
            "source": "memory",
        }
        for t in (list_tasks(uid) if uid else list_tasks())
    ]
    known = {t["task_id"] for t in merged}
    for pkg in list_packages():
        if pkg["task_id"] in known:
            continue
        if uid and not task_store.visible_to(str(pkg["task_id"]), uid):
            continue
        merged.append(
            {
                "task_id": pkg["task_id"],
                "product_name": pkg["product_name"],
                "status": "done",
                "stage": "完成",
                "platforms": pkg["platforms"],
                "owner_uid": task_store.owner_of(str(pkg["task_id"])) or "",
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
async def admin_stats(user: dict = Depends(cbauth.current_user)):
    """后台概览：任务量/状态分布/平台分布/合规与自愈指标（仅统计当前租户）。"""
    merged = _merged_tasks(cbauth.uid_of(user))
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
async def admin_tasks(limit: int = 20, user: dict = Depends(cbauth.current_user)):
    """后台任务列表（内存 + 磁盘，最近优先），仅列当前租户。"""
    merged = _merged_tasks(cbauth.uid_of(user))
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
                "owner_uid": t.get("owner_uid", ""),
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
async def submit_feedback(fb: Feedback, user: dict = Depends(cbauth.require_user)):
    """人类反馈：对单平台上架包打分（1=好评 / -1=差评），喂给记忆库与进化分析。"""
    if fb.rating not in (1, -1):
        raise HTTPException(status_code=422, detail="rating 只能为 1 或 -1")
    entry = memory_store.add_feedback(fb.task_id, fb.platform, fb.rating, fb.comment)
    return {"ok": True, "entry": entry}


@app.get("/api/agent/training-data")
async def training_data(user: dict = Depends(cbauth.require_user)):
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
async def skills_install(body: dict, user: dict = Depends(cbauth.require_user)):
    """从 https:// 或注册表目录内 file:// 拉取技能清单 → 白名单校验 → 落盘生效（规则 overlay + 工具注册）。"""
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
async def skills_uninstall(skill_id: str, user: dict = Depends(cbauth.require_user)):
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
async def evolve_now(user: dict = Depends(cbauth.require_user)):
    """手动触发一轮进化分析：读记忆+差评，产出提案待人工审批（不自动生效）。"""
    try:
        return {"result": await evolution.evolve(_get_client_cached())}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"进化分析失败: {exc}") from exc


@app.post("/api/agent/proposals/{pid}/approve")
async def proposal_approve(pid: str, user: dict = Depends(cbauth.require_user)):
    """批准即应用：prompt 补丁写提示词新版本，规则补丁写 overlay（均可回滚）。"""
    ok, detail = evolution.approve(pid)
    if not ok:
        raise HTTPException(status_code=400, detail=detail)
    return {"ok": True, "detail": detail}


@app.post("/api/agent/proposals/{pid}/reject")
async def proposal_reject(pid: str, user: dict = Depends(cbauth.require_user)):
    ok, detail = evolution.reject(pid)
    if not ok:
        raise HTTPException(status_code=400, detail=detail)
    return {"ok": True, "detail": detail}


@app.post("/api/agent/proposals/{pid}/rollback")
async def proposal_rollback(pid: str, user: dict = Depends(cbauth.require_user)):
    """回滚已生效提案：提示词还原上一版本 / 规则补丁移除。"""
    ok, detail = evolution.rollback(pid)
    if not ok:
        raise HTTPException(status_code=400, detail=detail)
    return {"ok": True, "detail": detail}
