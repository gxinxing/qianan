"""合规体检 Skill 实现 — 38+ 项确定性合规校验。

纯代码校验（非 LLM），图片规范用 PIL 实测；文字/水印等视觉语义项提示人工复核。
"""
from __future__ import annotations

import base64
import io
import logging
import re
import urllib.request
from dataclasses import dataclass
from typing import Any

from PIL import Image

from ..schemas import ComplianceIssue as DshComplianceIssue

logger = logging.getLogger(__name__)

_WORD_CACHE: dict[str, re.Pattern] = {}
_IMG_CACHE: dict[str, tuple[int, int, bool]] = {}


def _open_image(src: str) -> Image.Image:
    """URL 或 data URI → PIL Image。"""
    if src.startswith("data:"):
        _, _, payload = src.partition("base64,")
        return Image.open(io.BytesIO(base64.b64decode(payload))).convert("RGB")
    req = urllib.request.Request(src, headers={"User-Agent": "qianan-compliance"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return Image.open(io.BytesIO(resp.read())).convert("RGB")


def _measure_image(url: str) -> tuple[int, int, bool] | None:
    """下载主图用 PIL 实测：返回 (宽, 高, 四角是否近白)。"""
    if url in _IMG_CACHE:
        return _IMG_CACHE[url]
    try:
        im = _open_image(url)
        width, height = im.size
        patch = max(16, min(40, width // 50))
        boxes = [
            (0, 0, patch, patch),
            (width - patch, 0, width, patch),
            (0, height - patch, patch, height),
            (width - patch, height - patch, width, height),
        ]
        corners = []
        for box in boxes:
            px = list(im.crop(box).getdata())
            corners.append(tuple(round(sum(c[i] for c in px) / len(px)) for i in range(3)))
        bg_ok = all(min(c) >= 200 and (max(c) - min(c)) <= 30 for c in corners)
        result = (width, height, bg_ok)
        _IMG_CACHE[url] = result
        return result
    except Exception:
        return None


class ComplianceCheckSkill:
    """逐项执行 38+ 确定性合规校验。"""

    def __init__(self, config: dict | None = None, mock: bool | None = None) -> None:
        self.config = config or {}
        if mock is not None:
            self.config["mock"] = mock
        self.mock_mode = self.config.get("mock", False)

    async def run(
        self,
        listing: dict[str, Any],
        rules: dict[str, Any],
        category: str = "home_kitchen",
    ) -> dict[str, Any]:
        """对单个平台上架包执行全量合规校验。

        Args:
            listing: PlatformListing dict（title, bullets, description, attributes, images...）
            rules: 平台规则完整 dict（从 rules-engine skill 获取）
            category: 商品类目

        Returns:
            {platform, passed, issue_count, error_count, issues: [{check_id, severity, field, message}]}
        """
        platform = listing.get("platform", rules.get("platform", "unknown"))
        issues: list[DshComplianceIssue] = []

        for check in rules.get("complianceChecks", []):
            handler = getattr(self, f"_check_{check['type']}", None)
            if handler is None:
                continue
            found = handler(listing, rules, category, check)
            issues.extend(found)

        error_count = sum(1 for i in issues if i.severity == "error")
        return {
            "platform": platform,
            "passed": error_count == 0,
            "issue_count": len(issues),
            "error_count": error_count,
            "warn_count": len(issues) - error_count,
            "issues": [i.__dict__ for i in issues],
        }

    # ---------- 检查类型实现 ----------

    def _check_length(self, listing, rules, category, check) -> list[DshComplianceIssue]:
        value = listing.get(check.get("field", ""), "") or ""
        if isinstance(value, dict):
            value = str(value)
        limit = int(check.get("max", 0))
        if limit and len(str(value)) > limit:
            return [_issue(check, f"超出长度上限：{len(str(value))} > {limit} 字符")]
        return []

    def _check_length_each(self, listing, rules, category, check) -> list[DshComplianceIssue]:
        values = listing.get(check.get("field", ""), []) or []
        limit = int(check.get("max", 0))
        result = []
        for idx, item in enumerate(values):
            if limit and len(str(item)) > limit:
                result.append(_issue(check, f"第 {idx + 1} 条超长：{len(str(item))} > {limit} 字符", f"{check.get('field', '')}[{idx}]"))
        return result

    def _check_count(self, listing, rules, category, check) -> list[DshComplianceIssue]:
        values = listing.get(check.get("field", ""), []) or []
        lo, hi = check.get("min"), check.get("max")
        if lo is not None and len(values) < lo:
            return [_issue(check, f"数量不足：{len(values)} < {lo}")]
        if hi is not None and len(values) > hi:
            return [_issue(check, f"数量超限：{len(values)} > {hi}")]
        return []

    def _check_banned_words(self, listing, rules, category, check) -> list[DshComplianceIssue]:
        banned = rules.get("bannedWords", {})
        dict_name = check.get("dict", "")
        words = banned.get(dict_name, []) or []
        if not words:
            return []
        result = []
        for field in check.get("fields", []):
            text = listing.get(field, "") or ""
            if isinstance(text, list):
                text = " ".join(str(t) for t in text)
            lowered = str(text).lower()
            for word in words:
                pattern = _WORD_CACHE.setdefault(
                    word.lower(), re.compile(rf"(?<![a-z0-9]){re.escape(word.lower())}(?![a-z0-9])")
                )
                if pattern.search(lowered):
                    result.append(_issue(check, f"命中禁用词「{word}」（{dict_name} 组）", field))
        return result

    def _check_required_attrs(self, listing, rules, category, check) -> list[DshComplianceIssue]:
        required = rules.get("categoryAttributes", {}).get(category, [])
        attrs = listing.get("attributes", {}) or {}
        missing = [a for a in required if not attrs.get(a)]
        if missing:
            return [_issue(check, f"缺少必填类目属性：{', '.join(missing)}")]
        return []

    def _check_required_sections(self, listing, rules, category, check) -> list[DshComplianceIssue]:
        text = (listing.get(check.get("field", "description"), "") or "").lower()
        sections = check.get("sections", [])
        missing = [s for s in sections if s.lower() not in text]
        if missing:
            return [_issue(check, f"缺少必备段落：{', '.join(missing)}")]
        return []

    def _check_image_spec(self, listing, rules, category, check) -> list[DshComplianceIssue]:
        images = listing.get("images", []) or []
        if not images:
            return [_issue(check, "未生成主图，上架前需补充", "mainImage")]
        src = images[0]
        if src.startswith("mock://") or src.startswith("placeholder:"):
            return [_issue(check, "Mock 主图，跳过规范实测（实际部署后需真实生成）", "mainImage")]

        measured = _measure_image(src) if src.startswith("http") else None
        if measured is None and src.startswith("http"):
            return [_issue(check, "主图下载失败，建议人工复核", "mainImage")]

        result = []
        min_w = int(check.get("minWidth", 0))
        min_h = int(check.get("minHeight", 0))

        if measured:
            width, height, bg_ok = measured
            if (min_w or min_h) and (width < min_w or height < min_h):
                result.append(_issue(check, f"主图尺寸不足：实测 {width}×{height}，要求 ≥{min_w}×{min_h}", "mainImage"))
            bg = check.get("background")
            if bg == "white" and not bg_ok:
                result.append(_issue(check, "主图背景非纯白（四角采样），请更换", "mainImage"))
            if bg_ok and not result:
                result.append(_issue(check, f"尺寸 {width}×{height} 达标，白底通过；文字/水印建议复核", "mainImage"))
        return result or [_issue(check, "主图规范待图片生成后实测", "mainImage")]


def _issue(check: dict, message: str, field: str = "") -> DshComplianceIssue:
    return DshComplianceIssue(
        check_id=check["id"],
        severity=check.get("severity", "error"),
        field=field or check.get("field", ""),
        message=message,
    )


__all__ = ["ComplianceCheckSkill"]
