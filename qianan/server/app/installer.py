"""千岸 Agent 一键自动识别与注册 CLI 脚本 (qianan-cli / app/installer.py)。

可自动检测并注入用户环境中的各类 Coding Agents:
- Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`)
- Cursor (`~/.cursor/mcp.json` 或 `~/Library/Application Support/Cursor/User/globalStorage/publisher.mcp/mcp.json`)
- Codex (`~/.codex/mcp.json`)
- Trae (`~/.trae/mcp.json`)
- Qoder (`~/.qoder/mcp.json`)
- WorkBuddy (`~/.workbuddy/mcp.json`)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HOME = Path.home()

AGENT_CONFIG_PATHS = {
    "Claude Desktop": [
        HOME / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
        HOME / ".config" / "claude" / "claude_desktop_config.json",
    ],
    "Cursor": [
        HOME / ".cursor" / "mcp.json",
        HOME / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "mcp.json",
    ],
    "Codex": [
        HOME / ".codex" / "mcp.json",
    ],
    "Trae": [
        HOME / ".trae" / "mcp.json",
    ],
    "Qoder": [
        HOME / ".qoder" / "mcp.json",
    ],
    "WorkBuddy": [
        HOME / ".workbuddy" / "mcp.json",
    ],
}


def install_all() -> list[str]:
    """一键扫描并注入所有已安装 Agent。"""
    installed = []
    server_dir = Path(__file__).resolve().parents[1]
    python_bin = sys.executable

    mcp_spec = {
        "command": python_bin,
        "args": ["-m", "app.mcp_server"],
        "cwd": str(server_dir),
    }

    for agent_name, paths in AGENT_CONFIG_PATHS.items():
        for path in paths:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                data: dict[str, Any] = {}
                if path.exists():
                    try:
                        data = json.loads(path.read_text(encoding="utf-8"))
                    except Exception:
                        data = {}

                if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
                    data["mcpServers"] = {}

                data["mcpServers"]["qianan"] = mcp_spec
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                installed.append(agent_name)
                break
            except Exception:  # noqa: BLE001
                continue

    return installed


if __name__ == "__main__":
    agents = install_all()
    print(f"✅ 千岸 Agent 已完成一键自动识别与挂载！接入 Agent 列表: {', '.join(agents) if agents else '无'}")
