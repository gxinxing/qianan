"""合规检查 Agent — 调用 compliance-check skill 执行 Listing 逐项合规校验。"""
from __future__ import annotations

from skills.compliance_check.skill_impl import ComplianceCheckSkill


def create(config: dict | None = None) -> ComplianceCheckSkill:
    """工厂函数：DHC 按此签名创建 Agent 实例。"""
    return ComplianceCheckSkill(config=config)


__all__ = ["ComplianceCheckSkill", "create"]
