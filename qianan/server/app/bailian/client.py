"""阿里云百炼客户端封装（真实模式 + Mock 模式）。

网关链路（2026-09-15 实测，官方 dashscope 兼容模式）：
1. 文本模型走 /chat/completions（OpenAI 兼容），支持 enable_thinking: false 关闭思考加速响应。
   实测可用：qwen3.7-max（默认）、qwen-max / qwen-plus / qwen3.6-flash。
2. 图像生成**必须走下方万相原生端点**（`_dashscope_image_gen`）：
   官方兼容模式没有 /images/generations 路由（404），经 chat 列表 content 出图会
   返回 200 但 message 里既无 content 也无 image —— 静默失败，不可依赖。
3. 视觉理解（VL）在官方模式下可用：QIANAN_VL_MODEL=qwen3-vl-plus 实测能真实读图
   （旧 TokenDance 网关无 VL，商品理解只能走纯文本路径）。
4. 以图改图（图片编辑）已实测可用：content 列表追加 {"image": 参考图URL}，
   模型按提示词对参考图改写（白底化/场景化），保持商品本体不变。

历史：原网关 TokenDance（tokendance.space/gateway/v1）的 key 于 2026-09-15 返回
403 api_key_quota_exceeded，文本与图像同时不可用，已整体切换到官方端点。
"""
from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from typing import Protocol

import requests

logger = logging.getLogger(__name__)


def _load_server_env() -> None:
    """从 server/.env 加载配置（不覆盖已存在的环境变量）。"""
    from pathlib import Path

    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_server_env()

BASE_URL = os.getenv(
    "BAILIAN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
TEXT_MODEL = os.getenv("QIANAN_TEXT_MODEL", "qwen3.7-max")
IMAGE_MODEL = os.getenv("QIANAN_IMAGE_MODEL", "qwen-image-2.0")
#: 直连式图像网关（如 TokenDance seedream）的出图尺寸；部分模型有最小像素要求（如 ≥1920×1920）
IMAGE_SIZE = os.getenv("QIANAN_IMAGE_SIZE", "1024x1024")

#: 阿里云百炼原生直连（万相 wan2.7-image 等）。
#: 走兼容模式的 /images/generations 对**任何**图像模型都返回 404，
#: 万相必须走原生异步任务接口 /api/v1/services/aigc/... + Bearer 鉴权。
#: 留空 = 不启用，仍走上面的网关链路（seedream 等）。
DASHSCOPE_KEY = os.getenv("QIANAN_DASHSCOPE_API_KEY", "")
DASHSCOPE_NATIVE = "https://dashscope.aliyuncs.com/api/v1"
#: 百炼尺寸格式用星号（1024*1024），与直连式网关的 1024x1024 不同
DASHSCOPE_IMAGE_SIZE = os.getenv("QIANAN_DASHSCOPE_IMAGE_SIZE", "1024*1024")
#: 百炼专用模型名。必须与网关的 IMAGE_MODEL 分开 —— 万相走不通时要回退网关，
#: 而网关（TokenDance）并不认识 wan2.7-image，用同一个变量会让回退也一起失败。
DASHSCOPE_IMAGE_MODEL = os.getenv("QIANAN_DASHSCOPE_IMAGE_MODEL", "wan2.7-image")
#: 额度保护：入门套餐张数有限，用完自动回退网关而不再调万相。
#: 0 = 不限制。按 ¥0.2/张 估算，100 张 ≈ ¥20。
DASHSCOPE_IMAGE_QUOTA = int(os.getenv("QIANAN_DASHSCOPE_IMAGE_QUOTA", "100"))
#: 万相单次调用超时。出图正常 5–30s，60s 已经是很宽松的上限。
#: 曾被设为 180s —— 云端一旦在某张图上卡住（实测详情图非预期地不返回），
#: 180s 会被整段吃满且没有重试收益，直接拖垮整个 Agent 墙钟预算。
DASHSCOPE_TIMEOUT = int(os.getenv("QIANAN_DASHSCOPE_TIMEOUT", "60"))
#: 是否把出图 URL 转存到外部图床（litterbox）。
#: 默认**关闭**：该图床已对数据中心 IP 返回 403/412，转存 100% 失败，
#: 且每次失败都要白等满重试（实测单平台仅此一项就多耗 90s，吃光 Agent 墙钟预算）。
#: 关闭后直接使用万相返回的 OSS 签名 URL —— 其有效期足够覆盖演示与评审全程。
#: 将来接入可靠图床（如云存储）时置 1 即可恢复转存语义。
IMAGE_PERSIST = os.getenv("QIANAN_IMAGE_PERSIST", "0") == "1"
_QUOTA_FILE = "data/wan_image_quota.json"
_quota_lock = threading.Lock()


def _quota_used() -> int:
    """已消耗的万相出图张数（落盘，重启不丢）。"""
    try:
        return int(json.loads(open(_QUOTA_FILE, encoding="utf-8").read()).get("used", 0))
    except Exception:  # noqa: BLE001 —— 配额文件损坏不应影响主流程
        return 0


def _quota_allow(n: int = 1) -> bool:
    if DASHSCOPE_IMAGE_QUOTA <= 0:
        return True
    return _quota_used() + n <= DASHSCOPE_IMAGE_QUOTA


def _quota_consume(n: int = 1) -> None:
    """累加消耗。失败只记日志 —— 记账失败不该让已生成的图丢掉。"""
    if DASHSCOPE_IMAGE_QUOTA <= 0:
        return
    with _quota_lock:
        try:
            used = _quota_used() + n
            os.makedirs(os.path.dirname(_QUOTA_FILE) or ".", exist_ok=True)
            with open(_QUOTA_FILE, "w", encoding="utf-8") as fh:
                json.dump({"used": used, "quota": DASHSCOPE_IMAGE_QUOTA}, fh)
        except Exception as exc:  # noqa: BLE001
            logger.warning("万相额度记账失败: %s", exc)


def _public_ref(ref: str) -> str | None:
    """确保参考图是万相能下载到的公网 URL。

    万相服务端要主动去下载参考图，所以：
    - 公网 URL → 直接用
    - `data:` URL（上传图床失败时的回退形态）→ 阿里云下载不了，先转存成公网地址；
      转存也失败就返回 None —— 宁可退化成纯文生图，也不要提交一个必然报错的请求。
    """
    if not ref.startswith("data:"):
        return ref
    try:
        import base64 as _b64

        from .. import uploader

        raw = _b64.b64decode(ref.split(",", 1)[-1])
        url = uploader.upload_bytes(raw)
        logger.info("万相参考图为 data URL，已转存为公网地址")
        return url
    except Exception as exc:  # noqa: BLE001
        logger.warning("万相参考图转存失败，退化为纯文生图: %s", exc)
        return None


def _persist_image(url: str) -> str:
    """把万相返回的临时签名 URL 转存为持久地址。

    万相出图 URL 带 OSS 签名且会过期（Expires），直接交给前端会在若干小时后变死链。
    转存失败时**返回原 URL** —— 宁可将来过期，也不要当下没图。

    图床熔断后直接返回原 URL（连下载都省掉）：litterbox 对云函数出口 IP 返回 403，
    转存必然失败，若不短路则每张图都要白等一轮下载+上传重试（实测单步出图因此耗掉 384s）。
    """
    if not IMAGE_PERSIST:
        return url  # 默认关闭转存：直接用万相 OSS URL，见 IMAGE_PERSIST 说明

    from .. import uploader

    if uploader.is_circuit_open():
        return url
    try:
        raw = requests.get(url, timeout=60).content
        return uploader.upload_bytes(raw)
    except Exception as exc:  # noqa: BLE001
        logger.info("图片转存失败，使用原始 URL: %s", exc)
        return url

VL_MODEL = os.getenv("QIANAN_VL_MODEL", "")  # 留空 = 网关无 VL 模型
TIMEOUT = 180
# —— HTTP 重试：百炼网关偶发 429/5xx/超时抖动，避免整条 pipeline 因此直接失败 ——
_MAX_ATTEMPTS = 3       # 最多重试 2 次，共 3 次尝试
_RETRY_BACKOFF = 1.0     # 指数退避基数：两次重试分别等待约 1s / 2s（另加随机 jitter）
_RETRY_AFTER_CAP = 60.0  # 429 优先按 Retry-After 头等待，并截断到该上限（秒）


VIDEO_MODEL = os.getenv("QIANAN_VIDEO_MODEL", "wan2.7-i2v-2026-04-25")
VIDEO_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/api/v1"
)


class BailianLike(Protocol):
    is_mock: bool
    supports_vision: bool

    def chat(self, system: str, user: str, model: str | None = None) -> str: ...

    def chat_with_tools(self, messages: list[dict], tools: list[dict], model: str | None = None) -> dict: ...

    def image_gen(self, prompt: str, model: str | None = None, ref_image: str | None = None) -> str: ...

    def vision(self, image_ref: str, prompt: str, model: str | None = None) -> str: ...

    def video_gen(self, image_url: str, prompt: str, model: str | None = None) -> str: ...


class _AsyncImageUnsupported(RuntimeError):
    """网关不支持异步 images/generations 任务接口（用于回退 DashScope chat 格式）。"""


class BailianAuthFatal(RuntimeError):
    """鉴权/额度/欠费类致命错误（401/403、api_key_quota_exceeded、Arrearage 等）。

    这类错误不是网络抖动，重试无用，且一旦发生整个生成会硬崩。
    调用方（ResilientClient）捕获后可降级到 Mock 模式，保证演示流程不中断。
    """


#: 响应体中代表「重试无用、必须人工处理」的致命字样。
#: - api_key_quota_exceeded：阿里云额度上限（TokenDance 网关实测返回）
#: - Arrearage / overdue-payment：阿里云账户欠费（code 为 Arrearage，HTTP 400）
_FATAL_MARKERS = ("api_key_quota_exceeded", "Arrearage", "overdue-payment", "Free quota exhausted")


def _is_fatal_error(status: int, body: str) -> bool:
    """判断是否为鉴权/额度/欠费类致命错误（重试无用）。"""
    return status in (401, 403) or any(m in body for m in _FATAL_MARKERS)


# ---------------------------------------------------------------------------
# BYOK（Bring Your Own Key）：请求级密钥覆盖
#
# 场景：评委/访客没有服务端预置的 API Key（或预置额度已耗尽），可以在前端填自己的
# 百炼 Key，由请求头带到后端；该请求的所有模型调用改走他自己的额度。
#
# 实现用 ContextVar 而不是 os.environ：
#   - ContextVar 在 asyncio 中按 Task 隔离，FastAPI 每请求一个 Task，天然并发安全；
#   - 若临时改 os.environ，并发请求会互相覆盖 key（串号），绝不能那么做。
# 注：asyncio.create_task / to_thread 都会复制当前 context，所以密钥能正确传入
#     Agent 的后台任务与线程池。
# ---------------------------------------------------------------------------
from contextvars import ContextVar  # noqa: E402

_req_api_key: ContextVar[str | None] = ContextVar("qianan_req_api_key", default=None)
_req_dashscope_key: ContextVar[str | None] = ContextVar("qianan_req_dashscope_key", default=None)


def _api_key() -> str:
    """当前请求生效的文本/VL Key：请求级 BYOK > 服务端环境变量。"""
    return _req_api_key.get() or os.environ.get("BAILIAN_API_KEY", "")


def _dashscope_key() -> str:
    """当前请求生效的万相出图 Key：请求级 BYOK > 服务端环境变量。"""
    return _req_dashscope_key.get() or os.environ.get("QIANAN_DASHSCOPE_API_KEY", "")


def set_request_keys(api_key: str | None = None, dashscope_key: str | None = None) -> None:
    """在当前 context 绑定 BYOK 密钥。传空表示不覆盖，继续用服务端预置。"""
    if api_key:
        _req_api_key.set(api_key)
    if dashscope_key:
        _req_dashscope_key.set(dashscope_key)


def has_byok() -> bool:
    """当前请求是否携带了 BYOK 密钥（用于日志与响应标记）。"""
    return bool(_req_api_key.get() or _req_dashscope_key.get())


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }


def _resp_preview(resp) -> str:
    """响应体预览（用于错误信息）：能解析为 JSON 则序列化，否则取纯文本前 300 字符。"""
    try:
        return json.dumps(resp.json(), ensure_ascii=False)[:300]
    except ValueError:
        return (resp.text or "")[:300]


def _retry_delay(resp, attempt: int) -> float:
    """第 attempt 次尝试失败后的等待秒数：429 优先按 Retry-After 头，其余指数退避 + jitter。"""
    if resp is not None and resp.status_code == 429:
        raw = (resp.headers.get("Retry-After") or "").strip()
        if raw:
            try:
                after = float(raw)
                if after >= 0:
                    return min(after, _RETRY_AFTER_CAP)
            except ValueError:
                pass  # HTTP-date 等非数字格式 → 退回指数退避
    return _RETRY_BACKOFF * (2 ** (attempt - 1)) + random.uniform(0, 0.5)


def _post(payload: dict) -> dict:
    # 显式非流式：部分兼容网关（如 apimart.ai）在未传 stream 时默认返回 SSE
    # 分块，导致 resp.json() 解析崩溃。统一置 False 请求标准一次性 JSON。
    payload.setdefault("stream", False)
    url = f"{BASE_URL}/chat/completions"
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(url, headers=_headers(), json=payload, timeout=TIMEOUT)
        except (requests.Timeout, requests.ConnectionError) as exc:
            # 超时/连接错误：网关瞬时抖动所致；chat 推理接口无服务端副作用，重发安全。
            # 重试耗尽后保留原始异常类型原样抛出（与旧版行为一致）。
            if attempt == _MAX_ATTEMPTS:
                raise
            delay = _retry_delay(None, attempt)
            logger.warning(
                "百炼调用第 %d/%d 次尝试网络异常(%s): %s；%.1fs 后重试",
                attempt, _MAX_ATTEMPTS, type(exc).__name__, exc, delay,
            )
            time.sleep(delay)
            continue
        status = resp.status_code
        if status == 429 or status >= 500:
            # 明确可重试：限流/网关侧 5xx —— 请求被拒绝或未触达业务逻辑，均无副作用。
            if attempt == _MAX_ATTEMPTS:
                raise RuntimeError(f"百炼调用失败({status}): {_resp_preview(resp)}")
            delay = _retry_delay(resp, attempt)
            logger.warning(
                "百炼调用第 %d/%d 次尝试失败(%s): %s；%.1fs 后重试",
                attempt, _MAX_ATTEMPTS, status, _resp_preview(resp), delay,
            )
            resp.close()
            time.sleep(delay)
            continue
        # 其余状态码（200 正常 / 400、401 等明确参数或鉴权错误）不可重试；
        # JSON 解析失败同样不重试，维持原有解析与报错行为。
        data = resp.json()
        if status != 200 or "error" in data or (isinstance(data.get("code"), str) and "output" not in data):
            preview = json.dumps(data, ensure_ascii=False)[:300]
            # 鉴权/额度/欠费致命错误：重试无用，抛出专用异常交由 ResilientClient 降级 Mock
            if _is_fatal_error(status, preview):
                raise BailianAuthFatal(f"百炼调用鉴权/额度致命错误({status}): {preview}")
            raise RuntimeError(f"百炼调用失败({status}): {preview}")
        return data
    raise RuntimeError("百炼调用失败：重试循环意外退出")  # 防御性兜底，正常流程不可达


def _message_content(data: dict):
    """兼容 DashScope(output.choices) 与 OpenAI(chat/completions, choices) 两种返回结构，取出 message.content。"""
    choices = None
    if isinstance(data.get("output"), dict):
        choices = data["output"].get("choices")
    if not isinstance(choices, list) and isinstance(data.get("choices"), list):
        choices = data["choices"]
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(f"网关返回中无 choices: {str(data)[:200]}")
    # 用 .get 而非直接索引：官方兼容模式经 chat 通道出图时会返回 200、但 message 里
    # 既无 content 也无 image（usage 为 null）。直接索引会抛 KeyError 淹没真正原因，
    # 这里统一降级为 None，由调用方给出可诊断的报错。
    return (choices[0].get("message") or {}).get("content")


class BailianClient:
    """真实网关调用（同步；Agent 层用 asyncio.to_thread 包装）。"""

    is_mock = False

    def __init__(self) -> None:
        # 用 _api_key()（运行时取值）而非 os.environ：BYOK 场景下请求级 key 也要算数
        if not _api_key():
            raise RuntimeError("BAILIAN_API_KEY 未配置（服务端未预置，且本请求未携带 BYOK Key）")

    @property
    def supports_vision(self) -> bool:
        return bool(VL_MODEL)

    def chat(self, system: str, user: str, model: str | None = None) -> str:
        data = _post(
            {
                "model": model or TEXT_MODEL,
                "enable_thinking": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        )
        return data["choices"][0]["message"]["content"]

    def chat_with_tools(self, messages: list[dict], tools: list[dict], model: str | None = None) -> dict:
        """function calling：返回 assistant message（content 与 tool_calls 均可能为空/非空）。"""
        data = _post(
            {
                "model": model or TEXT_MODEL,
                "enable_thinking": False,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
            }
        )
        return data["choices"][0]["message"]

    def image_gen(self, prompt: str, model: str | None = None, ref_image: str | None = None) -> str:
        """图片生成，兼容三类网关：

        1. apimart.ai 等任务式网关：POST /images/generations 提交异步
           T2I 任务 → 轮询 GET /tasks/{id}（支持 image_url 参考图 = 以图改图）。
        2. TokenDance 等直连式网关：/images/generations 同步返回 data[].url。
        3. 官方 token-plan（DashScope compatible-mode）：/images/generations 不可用，
          须走 /chat/completions + content 列表 [{"text":...}, {"image": ref}]；
          该方法失败时自动回退该路径。
        """
        model = model or IMAGE_MODEL
        # ① 阿里云百炼原生（万相 wan2.7-image）：阿里自研、¥0.2/张，比赛场景优先。
        #    失败一律回退到网关链路，账户欠费/未配置都不会让任务缺图。
        if _dashscope_key():
            try:
                return self._dashscope_image_gen(prompt, DASHSCOPE_IMAGE_MODEL, ref_image)
            except Exception as exc:  # noqa: BLE001 —— 万相不可用必须静默降级
                logger.warning("百炼万相生图不可用，回退网关链路：%s", exc)
        try:
            return self._async_image_gen(prompt, model, ref_image)
        except _AsyncImageUnsupported:
            pass  # 网关不支持异步任务接口 → 回退 DashScope chat 格式
        content: list[dict] = [{"text": prompt}]
        if ref_image:
            content.append({"image": ref_image})
        data = _post(
            {
                "model": model,
                "messages": [{"role": "user", "content": content}],
            }
        )
        result = _message_content(data)
        if isinstance(result, str):
            return result
        if not result:
            raise RuntimeError(
                f"图片生成返回中无图片（该网关可能不支持经 chat 通道出图）: {str(data)[:200]}"
            )
        for part in result:
            if isinstance(part, dict) and part.get("image"):
                return part["image"]
        raise RuntimeError(f"图片生成返回中未找到图片: {str(result)[:200]}")

    def _dashscope_image_gen(self, prompt: str, model: str, ref_image: str | None) -> str:
        """阿里云百炼万相文生图（wan2.7-image / wan2.7-image-pro）。

        三个实测出来的关键点，改错任何一个都会失败：
        1. 端点是 `/services/aigc/multimodal-generation/generation`，
           不是 text2image/image-synthesis（后者一律报 "url error"）。
        2. **同步返回**，没有 task_id，结果直接在 output.choices[0].message.content 里。
        3. 鉴权用 `Authorization: Bearer`，用 X-DashScope-API-Key 报 No API-key provided。

        返回的图片 URL 是带 Expires 的 OSS 临时签名地址，必须转存，
        否则过期后前端拿到的是死链。
        """
        if not _quota_allow(1):
            raise RuntimeError(
                f"万相额度保护：已用 {_quota_used()}/{DASHSCOPE_IMAGE_QUOTA} 张，"
                f"达上限后自动回退网关，避免超出入门套餐"
            )
        headers = {
            "Authorization": f"Bearer {_dashscope_key()}",
            "Content-Type": "application/json",
        }
        content: list[dict] = [{"text": prompt}]
        ref = _public_ref(ref_image) if ref_image else None
        if ref:
            # 以图改图：参考图与提示词一起给（**图片在前、文字在后**），保持商品主体一致
            content = [{"image": ref}, {"text": prompt}]
        payload = {
            "model": model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": {"size": DASHSCOPE_IMAGE_SIZE, "n": 1},
        }
        url = f"{DASHSCOPE_NATIVE}/services/aigc/multimodal-generation/generation"
        # 万相偶发抖动（超时 / 5xx / 限流）是常态，而**回退链路在官方端点上兜不住**：
        # 兼容模式经 chat 出图会返回 200 但 message 里既无 content 也无 image，
        # 即一旦这里失败，这张图就彻底没救。所以重试必须做在万相本身上。
        last_err: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=DASHSCOPE_TIMEOUT)
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_err = exc
                if attempt == _MAX_ATTEMPTS:
                    raise
                delay = _retry_delay(None, attempt)
                logger.warning("万相调用第 %d/%d 次网络异常(%s)，%.1fs 后重试",
                               attempt, _MAX_ATTEMPTS, type(exc).__name__, delay)
                time.sleep(delay)
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                last_err = RuntimeError(f"万相调用失败({resp.status_code}): {resp.text[:200]}")
                if attempt == _MAX_ATTEMPTS:
                    raise last_err
                delay = _retry_delay(resp, attempt)
                logger.warning("万相调用第 %d/%d 次失败(%s)，%.1fs 后重试",
                               attempt, _MAX_ATTEMPTS, resp.status_code, delay)
                resp.close()
                time.sleep(delay)
                continue

            if resp.status_code >= 400:
                body = resp.text[:200]
                # 欠费/鉴权类重试无用，走致命错误通道（触发上层降级），其余参数错误直接抛
                if _is_fatal_error(resp.status_code, body):
                    raise BailianAuthFatal(f"万相鉴权/额度致命错误({resp.status_code}): {body}")
                raise RuntimeError(f"万相调用失败({resp.status_code}): {body}")

            data = resp.json() or {}
            choices = ((data.get("output") or {}).get("choices") or [{}])
            for part in ((choices[0].get("message") or {}).get("content") or []):
                if isinstance(part, dict) and part.get("image"):
                    _quota_consume(int((data.get("usage") or {}).get("image_count") or 1))
                    return _persist_image(part["image"])
            raise RuntimeError(f"万相返回中无图片: {str(data)[:200]}")
        raise RuntimeError(f"万相调用重试耗尽: {last_err}")  # 防御性兜底

    def _async_image_gen(self, prompt: str, model: str, ref_image: str | None) -> str:
        """异步任务式图片生成（apimart 等聚合网关），含提交与轮询。"""
        payload: dict = {"model": model, "prompt": prompt, "n": 1, "size": IMAGE_SIZE}
        if ref_image:
            payload["image_url"] = ref_image
        # 提交请求带网络级重试（与 _post 同策略）：直连式网关对 SSL/超时抖动敏感，
        # 一次抖动不应导致整个平台缺图（E2E 自检实测 amazon 因此缺图）
        resp = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                resp = requests.post(
                    f"{BASE_URL}/images/generations", headers=_headers(), json=payload, timeout=120
                )
                break
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt == _MAX_ATTEMPTS:
                    raise
                delay = _retry_delay(None, attempt)
                logger.warning(
                    "图片提交第 %d/%d 次尝试网络异常(%s)，%.1fs 后重试",
                    attempt, _MAX_ATTEMPTS, type(exc).__name__, delay,
                )
                time.sleep(delay)
        if resp is not None and _is_fatal_error(resp.status_code, resp.text or ""):
            raise BailianAuthFatal(f"图片生成鉴权/额度致命错误({resp.status_code}): {(resp.text or '')[:300]}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise _AsyncImageUnsupported(f"images/generations 非 JSON: {exc}") from exc
        if resp.status_code == 200 and "task_id" not in json.dumps(data, ensure_ascii=False):
            # 直连式网关（如 TokenDance seedream）：同步返回 data[].url，无任务轮询
            items = data.get("data") or []
            first = items[0] if isinstance(items, list) and items else None
            url = first.get("url") if isinstance(first, dict) else None
            if url:
                return url
            raise RuntimeError(f"直连式图片生成返回中未找到 URL: {str(data)[:200]}")
        if resp.status_code != 200 or "task_id" not in json.dumps(data, ensure_ascii=False):
            # 网关无该路由（如官方 token-plan）或任务提交失败
            err = str(data)[:200] if resp.status_code not in (404, 405) else "route not found"
            if resp.status_code in (404, 405):
                raise _AsyncImageUnsupported(err)
            raise RuntimeError(f"图片任务提交失败({resp.status_code}): {err}")
        tasks = (data.get("data") or [{}])
        tid = (tasks[0] if isinstance(tasks, list) else tasks).get("task_id") if tasks else None
        if not tid:
            raise RuntimeError(f"图片任务提交无 task_id: {str(data)[:200]}")

        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            time.sleep(4)
            try:
                r = requests.get(f"{BASE_URL}/tasks/{tid}", headers=_headers(), timeout=30)
            except (requests.Timeout, requests.ConnectionError):
                continue  # 轮询请求抖动直接进下一轮，不消耗任务进度
            try:
                d = (r.json() or {}).get("data") or {}
            except ValueError:
                continue
            status = d.get("status")
            if status == "completed":
                imgs = ((d.get("result") or {}).get("images") or [])
                if imgs:
                    url = (imgs[0].get("url") or "")
                    if isinstance(url, list):
                        url = url[0] if url else ""
                    if url:
                        return url
                raise RuntimeError(f"图片任务完成但无 URL: {str(d)[:200]}")
            if status in ("failed", "error", "cancelled"):
                raise RuntimeError(
                    f"图片任务 {status}: {d.get('error') or d.get('message') or '上游错误'}"
                )
        raise RuntimeError(f"图片生成超时（180s）: task {tid}")

    def vision(self, image_ref: str, prompt: str, model: str | None = None) -> str:
        """视觉理解：在显式配置 QIANAN_VL_MODEL 时使用（如 apimart gpt-4o）。

        注意：不能带 enable_thinking 等 DashScope 专属参数（OpenAI 兼容模型 400）。
        """
        if not VL_MODEL:
            raise NotImplementedError("当前网关无视觉理解模型，请配置 QIANAN_VL_MODEL 或使用文本理解路径")
        data = _post(
            {
                "model": model or VL_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": image_ref}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            }
        )
        message = data["choices"][0]["message"]
        content = message.get("content")
        if isinstance(content, list):
            return "".join(p.get("text", "") for p in content if isinstance(p, dict))
        return str(content)

    def video_gen(self, image_url: str, prompt: str, model: str | None = None) -> str:
        """图生视频（wan2.7-i2v）：基于商品主图生成 5 秒展示视频。

        DashScope 异步任务接口：
        1. POST /services/aigc/video-generation/video-synthesis 提交任务
        2. GET /tasks/{task_id} 轮询直到 SUCCEEDED
        """
        model = model or VIDEO_MODEL
        headers = {
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }
        payload = {
            "model": model,
            "input": {
                "image_url": image_url,
                "prompt": prompt,
            },
            "parameters": {
                "resolution": "720p",
                "duration": 5,
                "prompt_extend": True,
            },
        }
        # 提交任务
        submit_url = f"{VIDEO_BASE_URL}/services/aigc/video-generation/video-synthesis"
        resp = requests.post(submit_url, headers=headers, json=payload, timeout=120)
        data = resp.json()
        if resp.status_code != 200:
            raise RuntimeError(f"视频任务提交失败({resp.status_code}): {str(data)[:300]}")
        task_id = data.get("output", {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"视频任务提交无 task_id: {str(data)[:200]}")

        # 轮询
        poll_url = f"{VIDEO_BASE_URL}/tasks/{task_id}"
        deadline = time.monotonic() + 300  # 5 分钟超时
        while time.monotonic() < deadline:
            time.sleep(5)
            try:
                r = requests.get(poll_url, headers=headers, timeout=30)
                d = r.json()
            except (requests.Timeout, requests.ConnectionError, ValueError):
                continue
            status = d.get("output", {}).get("task_status", "")
            if status == "SUCCEEDED":
                video_url = d.get("output", {}).get("video_url")
                if video_url:
                    return video_url
                raise RuntimeError(f"视频任务成功但无 URL: {str(d)[:200]}")
            if status in ("FAILED", "UNKNOWN"):
                err = d.get("output", {}).get("message", "上游错误")
                raise RuntimeError(f"视频任务 {status}: {err}")
        raise RuntimeError(f"视频生成超时（300s）: task {task_id}")


class MockBailianClient:
    """模拟客户端：返回可读占位结果，供无 key 联调与演示兜底。"""

    is_mock = True
    supports_vision = False

    def chat(self, system: str, user: str, model: str | None = None) -> str:
        return f"[MOCK chat] 已收到指令（前 80 字）：{user[:80]}……"

    def chat_with_tools(self, messages: list[dict], tools: list[dict], model: str | None = None) -> dict:
        """脚本化工具调用：收到 tool 结果即收敛；否则对第一个工具发一次空参调用。"""
        if any(m.get("role") == "tool" for m in messages[-2:]):
            return {"content": "[MOCK] 工具循环已收敛", "tool_calls": []}
        if tools:
            fn = tools[0]["function"]
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": f"mock_call_{len(messages)}",
                        "type": "function",
                        "function": {"name": fn["name"], "arguments": "{}"},
                    }
                ],
            }
        return {"content": "[MOCK] 无工具可用", "tool_calls": []}

    def image_gen(self, prompt: str, model: str | None = None, ref_image: str | None = None) -> str:
        return "mock://generated-image"

    def vision(self, image_ref: str, prompt: str, model: str | None = None) -> str:
        return "[MOCK vision] 模拟商品理解结果。"

    def video_gen(self, image_url: str, prompt: str, model: str | None = None) -> str:
        return "mock://generated-video.mp4"


class _ResilientClient:
    """真实客户端包装：首次遇到鉴权/额度致命错误（BailianAuthFatal）时，
    自动降级到 MockBailianClient，保证生成流程不硬崩、演示不中断。

    降级是会话内一次性切换：一旦触发，后续所有调用都走 Mock，
    且 is_mock 翻为 True（/api/health 会如实反映）。
    正常运行（密钥有效）时行为与直接使用 BailianClient 完全一致。
    """

    is_mock = False

    def __init__(self, real: BailianLike) -> None:
        self._real = real
        self._mock: BailianLike | None = None

    @property
    def _active(self) -> BailianLike:
        return self._mock if self._mock is not None else self._real

    @property
    def supports_vision(self) -> bool:
        return self._active.supports_vision

    def _guard(self, method: str, *args, **kwargs):
        if self._mock is not None:
            return getattr(self._mock, method)(*args, **kwargs)
        try:
            return getattr(self._real, method)(*args, **kwargs)
        except BailianAuthFatal as exc:
            logger.warning("百炼网关鉴权/额度致命错误，自动降级 Mock 模式以保证演示可用：%s", exc)
            self._mock = MockBailianClient()
            self.is_mock = True
            return getattr(self._mock, method)(*args, **kwargs)

    def chat(self, *a, **k):
        return self._guard("chat", *a, **k)

    def chat_with_tools(self, *a, **k):
        return self._guard("chat_with_tools", *a, **k)

    def image_gen(self, *a, **k):
        return self._guard("image_gen", *a, **k)

    def vision(self, *a, **k):
        return self._guard("vision", *a, **k)

    def video_gen(self, *a, **k):
        return self._guard("video_gen", *a, **k)


def get_client() -> BailianLike:
    if os.getenv("QIANAN_MOCK", "0") == "1":
        logger.warning("QIANAN_MOCK=1，使用模拟百炼客户端")
        return MockBailianClient()
    if not _api_key():
        logger.warning("未配置 BAILIAN_API_KEY，自动进入 Mock 模式")
        return MockBailianClient()
    return _ResilientClient(BailianClient())


def resolve_image_ref(image_url: str | None, image_base64: str | None) -> str | None:
    """把上传图转为模型可用的引用：URL 直接用，base64 转 data URL；都没有则返回 None。"""
    if image_url:
        return image_url
    if image_base64:
        data = image_base64.split(",", 1)[-1]
        return f"data:image/jpeg;base64,{data}"
    return None
