"""千岸 QianAn — 自包含多租户身份认证（标准库实现，零外部依赖）。

为什么不用 CloudBase 内置鉴权
---------------------------
CloudBase Auth v2 需要 publishable key / clientId:clientSecret 才能签发与校验令牌，
本项目部署环境未配置该凭据，导致此前 `auth_ready()` 恒为 False、全员匿名、隔离失效。
改用标准库 PBKDF2(sha256) + HS256 JWT：注册 / 登录 / 按 uid 强制租户隔离全部自闭环，
可独立验证、无外部凭据依赖；同时保留 `current_user / require_user / uid_of` 接口，
`main.py` 与前端 `api.ts` 无需改动，后续若拿到 CloudBase 凭据也可平滑回退。

接口契约（与 main.py 保持一致）
--------------------------------
- auth_ready() -> bool
- REQUIRE_AUTH -> bool（模块级）
- current_user(request) -> dict        # FastAPI 依赖
- require_user(request) -> dict
- uid_of(user) -> str
- token_fingerprint(token) -> str
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException, Request

# ───────────────────── 配置 ─────────────────────
#: JWT 签名密钥：不设硬编码兜底（仓库里的常量等于公开密钥，任何人可伪造令牌）。
#: REQUIRE_AUTH 关闭时令牌仅用于展示登录态，留空可用；开启鉴权时缺失即启动失败。
JWT_SECRET = os.getenv("QIANAN_JWT_SECRET", "")
#: 需要登录才能写入（生成/发布/反馈）。默认 0 = 允许游客试用。
#: 演示（黑客松路演 / CloudBase 预览）依赖游客免登录直连，登录墙会卡死 demo 流程，故默认关闭。
REQUIRE_AUTH = os.getenv("QIANAN_REQUIRE_AUTH", "0") not in ("0", "false", "")
if REQUIRE_AUTH and not JWT_SECRET:
    # fail-fast：开启鉴权却没有独立密钥 = 要么全站拒登，要么弱密钥裸奔，都不如启动即炸
    raise RuntimeError(
        "QIANAN_REQUIRE_AUTH 已开启，但未设置 QIANAN_JWT_SECRET——"
        "拒绝以弱/空密钥签发 JWT。请配置该环境变量后重启。"
    )
ANON_UID = "anonymous"
TOKEN_TTL = int(os.getenv("QIANAN_TOKEN_TTL", "86400"))  # 24h
PW_MIN_LEN = 6
USER_MIN_LEN = 3

_USERS_FILE = Path(__file__).resolve().parents[1] / "data" / "users.json"
_USERS: dict[str, dict] = {}  # username(lower) -> {uid, username, salt, pw_hash}
_LOADED = False


# ───────────────────── 密码哈希（PBKDF2，标准库） ─────────────────────
def _hash_pw(password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return salt.hex(), dk.hex()


# ───────────────────── JWT（HS256，标准库） ─────────────────────
def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def issue_token(uid: str, username: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": uid,
        "username": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_TTL,
    }
    h = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h}.{p}".encode("ascii")
    sig = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url(sig)}"


def decode_token(token: str) -> Optional[dict]:
    try:
        h, p, s = token.split(".")
    except ValueError:
        return None
    signing_input = f"{h}.{p}".encode("ascii")
    expected = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    try:
        got = _b64url_decode(s)
    except Exception:
        return None
    if not hmac.compare_digest(expected, got):
        return None
    try:
        payload = json.loads(_b64url_decode(p))
    except Exception:
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return payload


# ───────────────────── 用户存储（带 /tmp 兜底） ─────────────────────
def _load_users() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    for path in (_USERS_FILE, Path("/tmp") / "qianan_users.json"):
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    _USERS.update(data)
                break
        except Exception:  # noqa: BLE001
            continue


def _save_users() -> None:
    _load_users()
    data = json.dumps(_USERS, ensure_ascii=False)
    for path in (_USERS_FILE, Path("/tmp") / "qianan_users.json"):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data, encoding="utf-8")
            return
        except Exception:  # noqa: BLE001 —— 只读文件系统降级到 /tmp
            continue


def create_user(username: str, password: str) -> dict:
    _load_users()
    uname = (username or "").strip().lower()
    if len(uname) < USER_MIN_LEN:
        raise ValueError(f"用户名至少 {USER_MIN_LEN} 个字符")
    if len(password or "") < PW_MIN_LEN:
        raise ValueError(f"密码至少 {PW_MIN_LEN} 位")
    if uname in _USERS:
        raise ValueError("该用户名已被注册")
    uid = uuid.uuid4().hex[:12]
    salt, pw_hash = _hash_pw(password)
    _USERS[uname] = {"uid": uid, "username": username, "salt": salt, "pw_hash": pw_hash}
    _save_users()
    return {"uid": uid, "username": username}


def authenticate(username: str, password: str) -> Optional[dict]:
    _load_users()
    rec = _USERS.get((username or "").strip().lower())
    if not rec:
        return None
    salt = bytes.fromhex(rec["salt"])
    _, expect = _hash_pw(password, salt)
    if not hmac.compare_digest(expect, rec["pw_hash"]):
        return None
    return {"uid": rec["uid"], "username": rec["username"]}


# ───────────────────── 请求解析 ─────────────────────
def _bearer_from_request(request: Request) -> str:
    header = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    # 下载类接口用 <a download> / <img> 直连，带不了 header，允许 query 兜底
    return (request.query_params.get("access_token") or "").strip()


# ───────────────────── FastAPI 依赖（接口契约） ─────────────────────
def auth_ready() -> bool:
    """自包含鉴权始终就绪。"""
    return True


def current_user(request: Request) -> dict:
    """解析当前请求身份。匿名时返回 anonymous 租户。"""
    token = _bearer_from_request(request)
    if token:
        payload = decode_token(token)
        if payload:
            username = payload.get("username") or ""
            return {
                "uid": str(payload.get("sub") or ANON_UID),
                "name": username,
                "username": username,
                "authenticated": True,
            }
        # 带了 token 但校验失败：不降级为匿名，避免越权混淆
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    if REQUIRE_AUTH:
        raise HTTPException(status_code=401, detail="请先登录")
    return {"uid": ANON_UID, "name": "", "username": "", "authenticated": False}


def require_user(request: Request) -> dict:
    """写操作必须实名（游客也可，但必须是有效会话）。"""
    user = current_user(request)
    if REQUIRE_AUTH and not user.get("authenticated"):
        raise HTTPException(status_code=401, detail="该操作需要登录")
    return user


def uid_of(user: dict) -> str:
    return str(user.get("uid") or ANON_UID)


def token_fingerprint(token: str) -> str:
    """日志用的 token 短指纹（不落明文）。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
