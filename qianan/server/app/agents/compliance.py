"""⑤ 合规体检 Agent：用规则库的 complianceChecks 做确定性校验。

规则驱动（长度/数量/禁词/必填属性/必备段落）是真代码校验，不是 LLM 瞎判；
图片规范用 PIL 实测（尺寸 + 四角白底采样），文字/水印等视觉语义项提示人工复核。
"""
from __future__ import annotations

import base64
import io
import re
import urllib.request

from PIL import Image

from ..schemas import ComplianceIssue, PlatformListing

_WORD_CACHE: dict[str, re.Pattern] = {}
_IMG_CACHE: dict[str, tuple[int, int, bool]] = {}


def _open_image(src: str) -> Image.Image:
    """URL 或 data URI → PIL Image（侧边栏表单场景图片以内联 base64 传来）。"""
    if src.startswith("data:"):
        _, _, payload = src.partition("base64,")
        return Image.open(io.BytesIO(base64.b64decode(payload))).convert("RGB")
    req = urllib.request.Request(src, headers={"User-Agent": "qianan-compliance"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return Image.open(io.BytesIO(resp.read())).convert("RGB")


def _measure_image(url: str) -> tuple[int, int, bool] | None:
    """下载主图用 PIL 实测：返回 (宽, 高, 四角是否近白)；失败返回 None。

    近白判定：每角采样块平均通道 min≥200 且通道差≤30 —— 能拦住彩色/深色背景，
    又不误伤 AI 生成图的柔和影棚白。结果按 URL 缓存，修订复检不重复下载。
    """
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
    except Exception:  # noqa: BLE001 —— 下载/解析失败降级为人工复核提示，不阻断流水线
        return None


class ComplianceAgent:
    def run(self, listing: PlatformListing, rules: dict, category: str) -> None:
        issues: list[ComplianceIssue] = []
        for check in rules.get("complianceChecks", []):
            handler = getattr(self, f"_check_{check['type']}", None)
            if handler is None:
                continue
            issues.extend(handler(listing, rules, category, check))
        listing.compliance = issues
        listing.compliance_passed = not any(i.severity == "error" for i in issues)

    # ---------- 各检查类型的实现 ----------

    @staticmethod
    def _resolve_limit(rules: dict, field: str) -> int:
        """从父级 rules 按 field 名解析长度上限（合规检查项本身不带 limit）。"""
        key = (field or "").lower()
        for section in ("title", "description"):
            val = rules.get(section, {})
            if section in key or key in section:
                return int(val.get("maxLength", 0))
        return 0

    def _check_length(self, listing, rules, category, check) -> list[ComplianceIssue]:
        field = check.get("field", "")
        value = getattr(listing, field, "") or ""
        if isinstance(value, list):
            value = " ".join(value)
        limit = self._resolve_limit(rules, field)
        if limit and len(value) > limit:
            return [
                ComplianceIssue(
                    check_id=check["id"],
                    severity=check.get("severity", "error"),
                    field=field,
                    message=f"超出长度上限：{len(value)} > {limit} 字符",
                )
            ]
        return []

    def _check_length_each(self, listing, rules, category, check) -> list[ComplianceIssue]:
        field = check.get("field", "")
        values = getattr(listing, field, []) or []
        limit = self._resolve_limit(rules, field)
        per_limit = int(rules.get("bullets", {}).get("maxLengthPer", limit))
        target = per_limit or limit
        if not target:
            return []
        issues = []
        for idx, item in enumerate(values):
            if len(item) > target:
                issues.append(
                    ComplianceIssue(
                        check_id=check["id"],
                        severity=check.get("severity", "error"),
                        field=f"{field}[{idx}]",
                        message=f"第 {idx + 1} 条超长：{len(item)} > {target} 字符",
                    )
                )
        return issues

    def _check_count(self, listing, rules, category, check) -> list[ComplianceIssue]:
        field = check.get("field", "")
        values = getattr(listing, field, []) or []
        bullets_rule = rules.get("bullets", {})
        lo = bullets_rule.get("count", 0) if bullets_rule.get("style") != "none" else None
        hi = bullets_rule.get("count")
        if lo is not None and len(values) < lo:
            return [
                ComplianceIssue(
                    check_id=check["id"],
                    severity=check.get("severity", "warn"),
                    field=field,
                    message=f"数量不足：{len(values)} < {lo}",
                )
            ]
        if hi is not None and len(values) > hi:
            return [
                ComplianceIssue(
                    check_id=check["id"],
                    severity=check.get("severity", "warn"),
                    field=field,
                    message=f"数量超限：{len(values)} > {hi}",
                )
            ]
        return []

    def _check_banned_words(self, listing, rules, category, check) -> list[ComplianceIssue]:
        banned = rules.get("bannedWords", {})
        # dict: 指定单组；空 = 扫描全部词组
        group_key = check.get("dict", "")
        if group_key:
            word_groups = {group_key: banned.get(group_key, [])}
        else:
            word_groups = {k: v for k, v in banned.items() if isinstance(v, list)}
        # fields: 指定扫描字段；空 = 用 check.field + 常见文案字段
        fields = check.get("fields") or [check.get("field", "title"), "bullets", "description"]
        issues = []
        for field in fields:
            text = getattr(listing, field, "") or ""
            if isinstance(text, list):
                text = " ".join(text)
            lowered = text.lower()
            for group_name, words in word_groups.items():
                for word in words:
                    pattern = _WORD_CACHE.setdefault(
                        word.lower(), re.compile(rf"(?<![a-z0-9]){re.escape(word.lower())}(?![a-z0-9])")
                    )
                    if pattern.search(lowered):
                        issues.append(
                            ComplianceIssue(
                                check_id=check["id"],
                                severity=check.get("severity", "error"),
                                field=field,
                                message=f"命中禁用词「{word}」（{group_name} 组）",
                            )
                        )
        return issues

    def _check_required_attrs(self, listing, rules, category, check) -> list[ComplianceIssue]:
        required = rules.get("categoryAttributes", {}).get(category, [])
        missing = [attr for attr in required if not listing.attributes.get(attr)]
        if missing:
            return [
                ComplianceIssue(
                    check_id=check["id"],
                    severity=check.get("severity", "warn"),
                    field="attributes",
                    message=f"缺少必填类目属性：{', '.join(missing)}",
                )
            ]
        return []

    def _check_required_sections(self, listing, rules, category, check) -> list[ComplianceIssue]:
        text = (getattr(listing, check.get("field", "description"), "") or "").lower()
        missing = [s for s in check.get("sections", []) if s.lower() not in text]
        if missing:
            return [
                ComplianceIssue(
                    check_id=check["id"],
                    severity=check.get("severity", "warn"),
                    field=check.get("field", ""),
                    message=f"缺少必备段落：{', '.join(missing)}",
                )
            ]
        return []

    def _check_image_spec(self, listing, rules, category, check) -> list[ComplianceIssue]:
        """主图规范实测：PIL 校验尺寸与四角白底（确定性）；文字/水印等视觉项提示人工复核。"""
        if not listing.images:
            return [
                ComplianceIssue(
                    check_id=check["id"],
                    severity="warn",
                    field="mainImage",
                    message="未生成主图，上架前需补充",
                )
            ]
        src = listing.images[0]
        if src.startswith("mock://"):
            return [
                ComplianceIssue(
                    check_id=check["id"],
                    severity="warn",
                    field="mainImage",
                    message="Mock 主图（未生成真实图片），跳过主图规范实测",
                )
            ]

        measured = _measure_image(src)
        if measured is None:
            return [
                ComplianceIssue(
                    check_id=check["id"],
                    severity="warn",
                    field="mainImage",
                    message="主图下载失败，本轮未做规范实测，建议人工复核",
                )
            ]

        width, height, bg_ok = measured
        issues: list[ComplianceIssue] = []
        mi = rules.get("mainImage", {})
        min_w = int(check.get("minWidth", mi.get("minWidth", 0)))
        min_h = int(check.get("minHeight", mi.get("minHeight", 0)))
        if (min_w or min_h) and (width < min_w or height < min_h):
            issues.append(
                ComplianceIssue(
                    check_id=check["id"],
                    severity="error",
                    field="mainImage",
                    message=f"主图尺寸不足：实测 {width}×{height}，平台要求 ≥{min_w}×{min_h}",
                )
            )
        bg = check.get("background", mi.get("background"))
        if bg and not bg_ok:
            severity = "error" if bg == "white" else "warn"
            label = "非纯白" if bg == "white" else "非浅色纯色"
            issues.append(
                ComplianceIssue(
                    check_id=check["id"],
                    severity=severity,
                    field="mainImage",
                    message=f"主图背景实测{label}（四角采样），请更换商品图或重新生成",
                )
            )
        if not issues:
            issues.append(
                ComplianceIssue(
                    check_id=check["id"],
                    severity="warn",
                    field="mainImage",
                    message=f"主图实测 {width}×{height}，白底通过；文字/水印/边框等视觉项建议人工或 Qwen-VL 复核",
                )
            )
        return issues

    def _check_locale_coverage(self, listing, rules, category, check) -> list[ComplianceIssue]:
        required = check.get("locales") or rules.get("locales", [])
        if required and listing.locales:
            missing = [l for l in required if l not in listing.locales]
            if missing:
                return [
                    ComplianceIssue(
                        check_id=check["id"],
                        severity=check.get("severity", "warn"),
                        field="locales",
                        message=f"缺少语言覆盖：{', '.join(missing)}",
                    )
                ]
        return []
