"""千岸跨境上新 Model Context Protocol (MCP) 服务端。

支持 stdio JSON-RPC 2.0 协议，供 Claude Desktop、Cursor、Codex、Pi 等外部 Agent 客户端一键接入；
免除用户在网页端繁琐配置各项 API Key 的痛点，让用户日常使用的 Agent 直接调度千岸的合规与上新能力。

运行方式：
    python -m app.mcp_server
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from .agents.compliance import ComplianceAgent
from .agents.copywriting import CopywritingAgent
from .agents.understanding import ProductUnderstandingAgent
from .bailian.client import get_client
from .economics import EconomicsInput, evaluate
from .rules_store import load_rules
from .schemas import GenerateRequest

SERVER_INFO = {
    "name": "qianan-crossborder-mcp",
    "version": "1.1.0",
    "description": "千岸一稿多岸跨境上新 Agent MCP 服务：合规体检、A9埋词、差评反切与出海经济测算",
}

TOOLS = [
    {
        "name": "qianan_understand_product",
        "description": "多模态深度理解跨境电商商品，提取类目、物理规格、目标客群与核心卖点档案",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_name": {"type": "string", "description": "商品名称"},
                "selling_points": {"type": "string", "description": "中文原始卖点"},
                "image_url": {"type": "string", "description": "商品白底主图 URL (可选)"},
            },
            "required": ["product_name", "selling_points"],
        },
    },
    {
        "name": "qianan_generate_listing",
        "description": "为指定平台（Amazon/Shopee/TikTok/速卖通/Lazada）生成合规 Listing（含 A9 词与差评反切矩阵）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "enum": ["amazon", "shopee", "tiktokshop", "aliexpress", "lazada"],
                    "description": "目标跨境电商平台",
                },
                "product_name": {"type": "string", "description": "商品名称"},
                "selling_points": {"type": "string", "description": "中文核心卖点"},
                "category": {"type": "string", "description": "商品类目 (如 home_kitchen, electronics, apparel)"},
            },
            "required": ["platform", "product_name", "selling_points"],
        },
    },
    {
        "name": "qianan_audit_compliance",
        "description": "对指定平台的 Listing 执行 47 项确定性合规排雷（字符数红线、违禁词扫描、侵权排查）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "platform": {"type": "string", "enum": ["amazon", "shopee", "tiktokshop", "aliexpress", "lazada"]},
                "title": {"type": "string", "description": "待检查标题"},
                "bullets": {"type": "array", "items": {"type": "string"}, "description": "待检查五点描述 (Amazon)"},
                "description": {"type": "string", "description": "待检查商品长描述"},
                "category": {"type": "string", "description": "商品类目"},
            },
            "required": ["platform", "title"],
        },
    },
    {
        "name": "qianan_calculate_economics",
        "description": "测算出海单位经济学（5 平台保本价、建议售价、物流抛重计费比、佣金与净利率）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cost_cny": {"type": "number", "description": "单件采购成本 (元)"},
                "weight_kg": {"type": "number", "description": "商品毛重 (kg)"},
                "length_cm": {"type": "number", "description": "外包装长 (cm)"},
                "width_cm": {"type": "number", "description": "外包装宽 (cm)"},
                "height_cm": {"type": "number", "description": "外包装高 (cm)"},
                "target_margin": {"type": "number", "default": 0.25, "description": "目标净利润率 (默认 0.25 即 25%)"},
            },
            "required": ["cost_cny", "weight_kg", "length_cm", "width_cm", "height_cm"],
        },
    },
]


async def handle_call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    client = get_client()

    if name == "qianan_understand_product":
        agent = ProductUnderstandingAgent(client)
        req = GenerateRequest(
            product_name=args["product_name"],
            selling_points=args["selling_points"],
            image_url=args.get("image_url") or None,
        )
        u = await agent.run(req)
        return u.model_dump()

    elif name == "qianan_generate_listing":
        platform = args["platform"]
        req = GenerateRequest(
            product_name=args["product_name"],
            selling_points=args["selling_points"],
            category=args.get("category") or "home_kitchen",
            platforms=[platform],
        )
        u_agent = ProductUnderstandingAgent(client)
        understanding = await u_agent.run(req)
        rules = load_rules(platform)

        cw_agent = CopywritingAgent(client)
        listing = await cw_agent.run(req, understanding, platform, rules)
        return listing.model_dump()

    elif name == "qianan_audit_compliance":
        platform = args["platform"]
        rules = load_rules(platform)
        from .schemas import PlatformListing
        category = args.get("category") or "home_kitchen"
        listing = PlatformListing(
            platform=platform,
            title=args.get("title", ""),
            bullets=args.get("bullets", []),
            description=args.get("description", ""),
        )
        comp_agent = ComplianceAgent()
        comp_agent.run(listing, rules, category)
        errors = [i.model_dump() for i in listing.compliance if i.severity == "error"]
        warns = [i.model_dump() for i in listing.compliance if i.severity == "warn"]
        return {
            "passed": len(errors) == 0,
            "error_count": len(errors),
            "warn_count": len(warns),
            "errors": errors,
            "warns": warns,
        }

    elif name == "qianan_calculate_economics":
        inp = EconomicsInput(
            cost_cny=args["cost_cny"],
            weight_kg=args["weight_kg"],
            length_cm=args["length_cm"],
            width_cm=args["width_cm"],
            height_cm=args["height_cm"],
            target_margin=args.get("target_margin", 0.25),
        )
        res = evaluate(inp)
        return res.model_dump()

    raise ValueError(f"未知工具: {name}")


def main() -> None:
    """Stdio JSON-RPC 2.0 loop."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": SERVER_INFO,
                },
            }
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()

        elif method == "notifications/initialized":
            pass

        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": TOOLS},
            }
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()

        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            try:
                result = asyncio.run(handle_call(tool_name, tool_args))
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}
                        ]
                    },
                }
            except Exception as e:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "isError": True,
                        "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    },
                }
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
