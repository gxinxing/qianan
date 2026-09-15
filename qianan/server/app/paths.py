"""统一路径解析 —— 兼容本地开发和 SCF 只读文件系统。

SCF 运行时代码目录 `/var/user` 是只读挂载，所有写入操作必须回退到
`QIANAN_DATA_DIR`（环境变量，默认 `/tmp/qianan-data`）。
只读资源（rules/skills/data 模板文件）优先探测代码目录，找不到则回退。

用法：
    from .paths import writable_dir, readonly_dir
    DATA_DIR = writable_dir("data", "memory")
    RULES_DIR = readonly_dir("rules")
"""
from __future__ import annotations

import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent  # app/
_PKG_ROOT = _HERE.parent                 # server/ (= /var/user on SCF)


def _tmp_root() -> Path:
    return Path(os.getenv("QIANAN_DATA_DIR", "/tmp/qianan-data"))


def _join(parts: tuple) -> Path:
    """接受 str/Path 可变参数或单个 Path/str，返回拼接后的 Path。"""
    if len(parts) == 1 and isinstance(parts[0], (Path, str)):
        return Path(parts[0])
    return Path(*parts)


def writable_dir(*parts) -> Path:
    """返回可写目录。优先包内（本地开发），只读则回退到 QIANAN_DATA_DIR。
    自动创建目录。"""
    rel = _join(parts)
    # 本地开发：包目录可写就直接用
    pkg_path = _PKG_ROOT / rel
    try:
        pkg_path.mkdir(parents=True, exist_ok=True)
        # 写测试只需 touch 成功即证明目录可写；不再 unlink 清理 ——
        # 删除临时文件在只读/受限环境下可能抛异常甚至中断进程，
        # 而残留一个 0 字节 .wtest 无副作用（已在 .gitignore 中忽略）。
        (pkg_path / ".wtest").touch()
        return pkg_path
    except (OSError, PermissionError):
        pass
    # SCF: 回退到 /tmp
    tmp_path = _tmp_root() / rel
    tmp_path.mkdir(parents=True, exist_ok=True)
    return tmp_path


def writable_file(*parts) -> Path:
    """返回可写文件路径（父目录自动创建）。"""
    rel = _join(parts)
    parent = writable_dir(rel.parent)
    return parent / rel.name


def readonly_dir(*parts) -> Path:
    """返回只读资源目录。优先包内，回退到上层。"""
    rel = _join(parts)
    # 1. env 覆盖
    env_val = os.getenv(f"QIANAN_{rel.name.upper()}_DIR", "")
    if env_val and Path(env_val).is_dir():
        return Path(env_val)
    # 2. 包内 (server/rel = /var/user/rel on SCF)
    pkg = _PKG_ROOT / rel
    if pkg.is_dir():
        return pkg
    # 3. 包上级 (parents[2] 场景)
    parent = _PKG_ROOT.parent / rel
    if parent.is_dir():
        return parent
    # 4. 默认返回包内路径（即使不存在，避免 NameError）
    return pkg
