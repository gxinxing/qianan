"""Skill 商店：技能 = 规则补丁（规则库 overlay）+ 新工具（动态注册）。

工具三种形态（manifest tools[].type）：
- prompt（默认）：参数插值进 system 模板，再跑一次 LLM；
- http：声明式外部 API 连接器——url 模板 + 参数映射 + 响应取值，真实发 HTTP；
- static：内置数据表原样返回（演示「拿到 key 后换 http 即可」的占位连接器）。

安装流程：fetch（file:// 或 https://）→ 白名单校验 → 落盘 installed/ →
规则 overlay 由 rules_store 在读取时合并（不改 rules/*.json 源），
tools 段注册进 agent_core.registry，规划器即可调用。
卸载即删文件 + 注销工具 + cache_clear，规则库还原。
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from .agent_core import registry
from .bailian.client import BailianLike
from .schemas import ALL_PLATFORMS

SKILLS_DIR = Path(__file__).resolve().parents[1] / "data" / "skills"
REGISTRY_DIR = SKILLS_DIR / "registry"
INSTALLED_DIR = SKILLS_DIR / "installed"

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
_TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")

_CHECK_TYPES = {"banned_words", "required_sections", "length", "count"}
_SEVERITIES = {"error", "warn"}
_TOOL_TYPES = {"prompt", "http", "static"}
_HTTP_METHODS = {"GET", "POST"}
_KINDS = {"skill", "connector"}  # skill=规则补丁/提示词工具；connector=外部数据源（http/static 工具）
_FETCH_TIMEOUT = 10
_HTTP_TOOL_TIMEOUT = 8


def fetch_manifest(source: str) -> dict:
    """从 file:// 路径或 https:// URL 拉取技能清单。"""
    parsed = urlparse(source)
    if parsed.scheme in ("file", "") or source.startswith("/"):
        path = Path(parsed.path if parsed.scheme == "file" else source)
        if not path.is_file():
            raise ValueError(f"技能文件不存在: {source}")
        return json.loads(path.read_text(encoding="utf-8"))
    if parsed.scheme == "https":
        resp = requests.get(source, timeout=_FETCH_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    raise ValueError(f"不支持的技能来源（仅支持 file:// 或 https://）: {source}")


def validate_manifest(m: dict) -> list[str]:
    """白名单校验：任何非法字段都拒绝安装，返回错误列表（空 = 通过）。"""
    errors: list[str] = []
    sid = m.get("id", "")
    if not isinstance(sid, str) or not _ID_RE.match(sid):
        errors.append("id 必须为小写字母数字短横线（2-40 位）")
    if not str(m.get("name", "")).strip():
        errors.append("缺少 name")
    overlay = m.get("overlay")
    if overlay is not None:
        if not isinstance(overlay, dict):
            errors.append("overlay 必须是对象")
        else:
            for platform, patch in overlay.items():
                if platform not in ALL_PLATFORMS:
                    errors.append(f"overlay 含未知平台: {platform}")
                    continue
                if not isinstance(patch, dict):
                    errors.append(f"overlay[{platform}] 必须是对象")
                    continue
                if not isinstance(patch.get("bannedWords", {}), dict):
                    errors.append(f"overlay[{platform}].bannedWords 必须是对象")
                for check in patch.get("complianceChecks", []):
                    if not isinstance(check, dict) or check.get("type") not in _CHECK_TYPES:
                        errors.append(f"overlay[{platform}] 含非法检查项（type 白名单: {sorted(_CHECK_TYPES)}）")
                    elif check.get("severity", "error") not in _SEVERITIES:
                        errors.append(f"overlay[{platform}] 检查项 severity 非法")
    if m.get("kind", "skill") not in _KINDS:
        errors.append(f"kind 仅支持: {sorted(_KINDS)}")
    for tool in m.get("tools", []):
        if not isinstance(tool, dict) or not _TOOL_NAME_RE.match(str(tool.get("name", ""))):
            errors.append("tools[].name 必须为小写字母开头（a-z0-9_，2-40 位）")
            continue
        tname = tool.get("name")
        if not str(tool.get("description", "")).strip():
            errors.append(f"tools[{tname}] 缺少 description")
        if not isinstance(tool.get("parameters", {}), dict):
            errors.append(f"tools[{tname}] parameters 必须是对象")
        ttype = tool.get("type", "prompt")
        if ttype not in _TOOL_TYPES:
            errors.append(f"tools[{tname}] type 非法（白名单: {sorted(_TOOL_TYPES)}）")
        elif ttype == "prompt" and not str(tool.get("system", "")).strip():
            errors.append(f"tools[{tname}] 缺少 system 提示词模板")
        elif ttype == "http":
            if not str(tool.get("url", "")).startswith("https://"):
                errors.append(f"tools[{tname}] http 工具 url 必须为 https://（白名单出网）")
            if str(tool.get("method", "GET")).upper() not in _HTTP_METHODS:
                errors.append(f"tools[{tname}] method 仅支持 {sorted(_HTTP_METHODS)}")
        elif ttype == "static" and not isinstance(tool.get("data"), (dict, list)):
            errors.append(f"tools[{tname}] static 工具缺少 data 数据表（对象或数组）")
    return errors


def install_manifest(m: dict) -> dict:
    """校验并落盘；非法清单抛 ValueError（不落盘）。"""
    errors = validate_manifest(m)
    if errors:
        raise ValueError("；".join(errors))
    INSTALLED_DIR.mkdir(parents=True, exist_ok=True)
    path = INSTALLED_DIR / f"{m['id']}.json"
    if path.exists():
        raise ValueError(f"技能已安装: {m['id']}")
    path.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    _register_tools(m)
    from . import rules_store

    rules_store.cache_clear()
    return m


def uninstall(skill_id: str) -> bool:
    path = INSTALLED_DIR / f"{skill_id}.json"
    if not path.exists():
        return False
    try:
        m = json.loads(path.read_text(encoding="utf-8"))
        for tool in m.get("tools", []):
            registry.unregister(str(tool.get("name", "")))
    except (json.JSONDecodeError, OSError):
        pass
    path.unlink(missing_ok=True)
    from . import rules_store

    rules_store.cache_clear()
    return True


def list_installed() -> list[dict]:
    out: list[dict] = []
    if not INSTALLED_DIR.is_dir():
        return out
    for path in sorted(INSTALLED_DIR.glob("*.json")):
        try:
            m = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out.append(
            {
                "id": m.get("id"),
                "name": m.get("name"),
                "version": m.get("version", ""),
                "kind": m.get("kind", "skill"),
                "description": m.get("description", ""),
                "platforms": sorted((m.get("overlay") or {}).keys()),
                "tools": [
                    {
                        "name": t.get("name"),
                        "type": t.get("type", "prompt"),
                        "description": t.get("description", ""),
                    }
                    for t in m.get("tools", [])
                ],
                "installed_at": path.stat().st_mtime,
            }
        )
    return out


def list_registry() -> list[dict]:
    """本地技能目录（演示「从网上获取」的源）：返回未安装技能的元信息。"""
    installed = {s["id"] for s in list_installed()}
    out: list[dict] = []
    if not REGISTRY_DIR.is_dir():
        return out
    for path in sorted(REGISTRY_DIR.glob("*.json")):
        try:
            m = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out.append(
            {
                "id": m.get("id"),
                "name": m.get("name"),
                "version": m.get("version", ""),
                "kind": m.get("kind", "skill"),
                "description": m.get("description", ""),
                "source": f"file://{path}",
                "installed": m.get("id") in installed,
            }
        )
    return out


def is_installed(skill_id: str) -> bool:
    """点亮开关：消费侧（economics/ideation）据此决定用实时数据还是内置兜底。"""
    return (INSTALLED_DIR / f"{skill_id}.json").is_file()


def _manifests() -> list[dict]:
    out: list[dict] = []
    if not INSTALLED_DIR.is_dir():
        return out
    for path in sorted(INSTALLED_DIR.glob("*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return out


EVOLUTION_OVERLAYS_DIR = Path(__file__).resolve().parents[1] / "data" / "evolution" / "overlays"


def rules_patch(platform: str) -> dict:
    """该平台的规则补丁合集 = 已安装技能 + 进化 Agent 批准的补丁（空 = 无补丁）。"""
    patch: dict = {}
    for m in _manifests():
        p = (m.get("overlay") or {}).get(platform)
        if isinstance(p, dict):
            patch = _merge_patch(patch, p)
    if EVOLUTION_OVERLAYS_DIR.is_dir():
        for path in sorted(EVOLUTION_OVERLAYS_DIR.glob("*.json")):
            try:
                o = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if o.get("platform") == platform and isinstance(o.get("patch"), dict):
                patch = _merge_patch(patch, o["patch"])
    return patch


def _merge_patch(base: dict, patch: dict) -> dict:
    merged = dict(base)
    for group, words in (patch.get("bannedWords") or {}).items():
        if not isinstance(words, list):
            continue
        existing = list(merged.get("bannedWords", {}).get(group) or [])
        existing.extend(str(w) for w in words if str(w) not in existing)
        merged.setdefault("bannedWords", {})[group] = existing
    for check in patch.get("complianceChecks") or []:
        if isinstance(check, dict):
            merged.setdefault("complianceChecks", []).append(check)
    return merged


def _register_tools(m: dict) -> None:
    for tool in m.get("tools", []):
        name = str(tool.get("name", ""))
        if not _TOOL_NAME_RE.match(name) or registry.get(name):
            continue
        factory = _TOOL_FACTORIES.get(str(tool.get("type", "prompt")), _make_prompt_tool)
        registry.register(
            registry.ToolSpec(
                name=name,
                description=str(tool.get("description", ""))[:300],
                parameters=tool.get("parameters") or {"type": "object", "properties": {}},
                handler=factory(tool),
                source=str(m.get("id", "skill")),
            )
        )


def _make_prompt_tool(tool: dict):
    """prompt 型工具：模型传来的参数填进 system 模板，跑一次 chat 返回文本。"""
    system_tpl = str(tool.get("system", ""))

    async def handler(**kwargs) -> str:
        from .bailian.client import get_client

        client: BailianLike = get_client()
        if client.is_mock:
            return f"[mock] 工具 {tool.get('name')} 已执行。入参：{json.dumps(kwargs, ensure_ascii=False)[:150]}"
        filled = system_tpl
        for k, v in list(kwargs.items())[:10]:
            filled = filled.replace("{" + str(k) + "}", str(v)[:1000])
        return await asyncio.to_thread(client.chat, filled, "请直接输出检查结果。")

    return handler


def _make_http_tool(tool: dict):
    """http 型工具（声明式连接器）：url 模板插值路径参数 → 真实发 HTTP → 按 response_path 点路径取值。

    - url 中的 {param} 占位符由入参填充（路径参数）；
    - 其余入参 GET 进 query、POST 进 JSON body；
    - response_path 如 "rates.CNY" 逐层取值，取不到则返回全量 JSON（截断）；
    - 网络/状态码错误不抛出，返回 [connector-error] 文本让模型自行降级。
    """
    url_tpl = str(tool.get("url", ""))
    method = str(tool.get("method", "GET")).upper()
    response_path = str(tool.get("response_path", "")).strip()

    async def handler(**kwargs) -> str:
        url = url_tpl
        used: set[str] = set()
        for k, v in list(kwargs.items())[:10]:
            token = "{" + str(k) + "}"
            if token in url:
                url = url.replace(token, str(v)[:200])
                used.add(k)
        params = {k: v for k, v in list(kwargs.items())[:10] if k not in used}
        query = (params or None) if method == "GET" else None
        body = (params or None) if method == "POST" else None
        try:
            resp = await asyncio.to_thread(
                requests.request,
                method,
                url,
                params=query,
                json=body,
                timeout=_HTTP_TOOL_TIMEOUT,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            return f"[connector-error] {tool.get('name')} 请求失败: {exc}"
        try:
            data = resp.json()
        except ValueError:
            # 非 JSON（如 RSS/XML 趋势 feed）：保留足够长度给消费侧正则提取
            return resp.text[:12000]
        node = data
        for key in [p for p in response_path.split(".") if p]:
            if isinstance(node, dict) and key in node:
                node = node[key]
            elif isinstance(node, list) and key.isdigit() and int(key) < len(node):
                node = node[int(key)]
            else:
                node = data
                break
        return json.dumps(node, ensure_ascii=False)[:800]

    return handler


def _make_static_tool(tool: dict):
    """static 型工具：内置数据表原样返回——占位连接器，拿到 key 后把 type 改成 http 即可上线。"""
    payload = json.dumps(tool.get("data"), ensure_ascii=False)

    async def handler(**kwargs) -> str:  # noqa: ARG001
        return payload[:800]

    return handler


_TOOL_FACTORIES = {
    "prompt": _make_prompt_tool,
    "http": _make_http_tool,
    "static": _make_static_tool,
}


def ensure_registered() -> None:
    """后端重启后注册表会清空：按已安装清单重新注册（幂等）。"""
    for m in _manifests():
        _register_tools(m)


def skill_tools() -> list:
    """已安装技能注册的新工具（由规划器按商品/市场上下文决定是否调用）。"""
    ensure_registered()
    ids = {m.get("id") for m in _manifests()}
    return [t for t in registry.all_tools() if t.source in ids]
