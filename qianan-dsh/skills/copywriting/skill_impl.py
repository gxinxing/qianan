"""文案生成 Skill 实现 — 多平台多语言 Listing 文案生成 + 自愈修订。"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from .. import constraint_brief, load_rules
from ..schemas import ComplianceIssue
from ..prompts import load as load_prompt

logger = logging.getLogger(__name__)

MOCK_BANNED = {
    "promotional": ["sale", "free shipping", "discount", "promotion", "coupon"],
    "claims": ["best", "#1", "top", "guarantee", "proven", "miracle"],
}


class CopywritingSkill:
    """按平台规则生成合规 Listing 文案，自愈修订。"""

    def __init__(self, config: dict | None = None, mock: bool | None = None) -> None:
        self.config = config or {}
        if mock is not None:
            self.config["mock"] = mock
        self.mock_mode = self.config.get("mock", False)

    async def run(
        self,
        understanding: dict[str, Any],
        platform: str,
        rules: dict[str, Any] | None = None,
        focus: str = "",
    ) -> dict[str, Any]:
        """生成单平台上架文案。

        Args:
            understanding: 商品理解结果（product_understanding skill 产出）
            platform: 平台 key
            rules: 平台规则（从 rules-engine skill 获取）
            focus: 调度 Agent 规划的生成要点

        Returns:
            PlatformListing dict
        """
        if not rules:
            rules = load_rules(platform)
        locales = rules.get("locales", ["en-US"])

        if self.mock_mode:
            return self._mock(understanding, platform, rules, locales)

        client = self.config.get("client")
        if not client:
            return self._mock(understanding, platform, rules, locales)

        system = load_prompt("copywriting_system") or self._default_system()
        banned_block = self._banned_words_block(rules)
        lessons_block = self._lessons_block(platform)
        user = self._build_prompt(understanding, platform, rules, locales, focus, banned_block, lessons_block)

        raw = await asyncio.to_thread(client.chat, system, user)
        data = self._parse_json(raw)
        return self._to_listing(platform, rules, locales, data)

    async def revise(
        self, listing: dict[str, Any], rules: dict[str, Any], issues: list[dict]
    ) -> dict[str, Any]:
        """合规自愈：按体检出的 error 修订文案。

        Args:
            listing: 当前 PlatformListing
            rules: 平台规则
            issues: compliance-check 返回的 issues 列表

        Returns:
            修订后的 PlatformListing
        """
        if self.mock_mode:
            return self._revise_local(listing, rules)

        client = self.config.get("client")
        if not client:
            return self._revise_local(listing, rules)

        issues_text = "\n".join(f"- 字段 {i['field']}：{i['message']}" for i in issues if i.get("severity") == "error")
        system = load_prompt("copywriting_revise_system") or self._default_revise_system()
        user = f"""修订 {rules.get('displayName', listing.get('platform'))} 平台的上架文案。

当前文案（JSON）：
{json.dumps({k: listing.get(k) for k in ['title', 'bullets', 'description', 'attributes', 'aplus']}, ensure_ascii=False, indent=2)}

合规体检反馈（必须全部修复）：
{issues_text}

平台规则约束：
{constraint_brief(rules)}

输出修订后的完整 JSON（与输入同结构）。"""

        raw = await asyncio.to_thread(client.chat, system, user)
        data = self._parse_json(raw)
        revised = dict(listing)
        for key in ("title", "description"):
            if data.get(key):
                revised[key] = data[key]
        if isinstance(data.get("bullets"), list):
            revised["bullets"] = [str(b) for b in data["bullets"]]
        if isinstance(data.get("attributes"), dict):
            revised["attributes"] = {str(k): str(v) for k, v in data["attributes"].items()}
        revised["revised_count"] = (listing.get("revised_count") or 0) + 1
        return revised

    # ---------- Mock 模式 ----------

    def _mock(self, understanding, platform, rules, locales) -> dict[str, Any]:
        kw = understanding.get("keywords") or [understanding.get("product_type", platform)]
        sp = understanding.get("selling_points") or ["premium quality"]
        base_title = f"{understanding.get('product_type', 'Product')} - {', '.join(sp[:2])}"
        title = {}
        description = {}
        first = locales[0]
        for locale in locales:
            lang = locale.split("-")[0]
            t = base_title if lang == "en" else f"[{lang}] {base_title}"
            title[locale] = t[: int(rules.get("title", {}).get("maxLength", 200))]
            description[locale] = (f"{t}. " + " | ".join(sp))[: int(rules.get("description", {}).get("maxLength", 2000))]

        bullets = self._mock_bullets(kw, sp, rules)
        return {
            "platform": platform,
            "display_name": rules.get("displayName", platform),
            "locales": locales,
            "title": title.get(first, title.get("en-US", "")),
            "bullets": bullets,
            "description": description.get(first, description.get("en-US", "")),
            "attributes": understanding.get("attributes", {}),
            "aplus": self._mock_aplus(understanding),
            "revised_count": 0,
            "compliance_passed": True,
        }

    def _mock_bullets(self, kw, sp, rules):
        count = rules.get("bullets", {}).get("count", 5)
        per = rules.get("bullets", {}).get("maxLengthPer", 500)
        return [f"{kw[i % len(kw)].title()} - {sp[i % len(sp)]}"[:per] for i in range(count)]

    def _mock_aplus(self, understanding) -> list[dict]:
        pt = understanding.get("product_type", "Our Product")
        sp = understanding.get("selling_points") or ["Quality design"]
        return [
            {"type": "headline", "title": pt.title(), "text": "Thoughtfully designed for everyday life."},
            {"type": "grid", "title": "Why You'll Love It", "items": [
                {"title": kw.title(), "text": sp[i]} for i, kw in enumerate(sp[:3])
            ]},
            {"type": "compare", "title": "Specifications", "items": [
                {"label": k, "value": v} for k, v in list(understanding.get("attributes", {}).items())[:4]
            ]},
            {"type": "story", "title": "Our Promise", "text": "We design practical products for modern life."},
        ]

    def _revise_local(self, listing, rules) -> dict[str, Any]:
        """Mock 自愈：剔除禁用词 + 截断超长。"""
        banned = [w for group in MOCK_BANNED.values() if isinstance(group, list) for w in group]
        revised = dict(listing)
        title_limit = int(rules.get("title", {}).get("maxLength", 200))
        desc_limit = int(rules.get("description", {}).get("maxLength", 2000))

        def clean(text: str) -> str:
            for word in banned:
                text = re.sub(rf"(?<![a-z0-9]){re.escape(word.lower())}(?![a-z0-9])", "", text, flags=re.IGNORECASE)
            return re.sub(r"\s{2,}", " ", text).strip(" -·|")

        def cap(text: str, limit: int) -> str:
            return text if not limit or len(text) <= limit else text[:limit - 1].rstrip() + "…"

        revised["title"] = cap(clean(revised.get("title", "")), title_limit)
        revised["description"] = cap(clean(revised.get("description", "")), desc_limit)
        revised["revised_count"] = (listing.get("revised_count") or 0) + 1
        return revised

    # ---------- Helpers ----------

    def _build_prompt(self, understanding, platform, rules, locales, focus, banned_block, lessons_block):
        first = locales[0] if locales else "en-US"
        template = """为以下商品生成 {platform} 平台上架文案。

商品理解（JSON）：
{understanding_json}

平台规则约束：
{constraints}

输出严格 JSON：
{{
  "locales": {locales_json},
  "title": {{ "<locale>": "本地化标题" }},
  "bullets": ["五点描述"],
  "description": {{ "<locale>": "本地化描述" }},
  "attributes": {{ "属性名": "值" }},
  "aplus": [
    {{"type": "headline", "title": "详情页首屏横幅主标题", "text": "副标题"}},
    {{"type": "grid", "title": "卖点区块标题", "items": [
      {{"title": "卖点小标题", "text": "一行说明"}},
      {{"title": "卖点小标题", "text": "一行说明"}},
      {{"title": "卖点小标题", "text": "一行说明"}}
    ]}},
    {{"type": "compare", "title": "规格参数", "items": [{{"label": "参数名", "value": "参数值"}}]}},
    {{"type": "story", "title": "品牌故事标题", "text": "2-3 句品牌故事"}}
  ]
}}
目标语言：{target_langs}。标题与描述必须遵守字符上限，禁止出现规则中的禁用词。
{focus_block}{lessons_block}"""
        return template.format(
            platform=rules.get("displayName", platform),
            understanding_json=json.dumps(understanding, ensure_ascii=False),
            constraints=constraint_brief(rules),
            locales_json=json.dumps(locales),
            target_langs=", ".join(locales),
            focus_block=(f"\n生成要点：{focus}" if focus else ""),
            lessons_block=lessons_block,
        )

    def _parse_json(self, raw: str) -> dict:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        start = text.find("{")
        if start < 0:
            raise ValueError(f"文案输出无法解析: {text[:200]}")
        candidates = [text[start:], re.sub(r",\s*([}\]])", r"\1", text[start:])]
        for cand in candidates:
            try:
                return json.loads(cand)
            except json.JSONDecodeError:
                continue
        decoder = json.JSONDecoder()
        for i in range(start, len(text)):
            if text[i] == "{":
                try:
                    obj, _ = decoder.raw_decode(text, i)
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    continue
        raise ValueError(f"文案输出无法解析: {text[:200]}")

    def _to_listing(self, platform, rules, locales, data) -> dict[str, Any]:
        first = locales[0] if locales else "en-US"
        titles = data.get("title") or {}
        descs = data.get("description") or {}
        title = self._first_locale(titles, first)
        desc = self._first_locale(descs, first)
        if isinstance(descs, str):
            desc = descs
        return {
            "platform": platform,
            "display_name": rules.get("displayName", platform),
            "locales": locales,
            "title": str(title),
            "bullets": [str(b) for b in (data.get("bullets") or [])],
            "description": str(desc),
            "attributes": {str(k): str(v) for k, v in (data.get("attributes") or {}).items()},
            "aplus": self._parse_aplus(data.get("aplus")),
            "revised_count": 0,
            "compliance_passed": True,
        }

    def _first_locale(self, container, first):
        if isinstance(container, dict):
            return container.get(first) or container.get("en-US", "") or next(iter(container.values()), "")
        return ""

    def _parse_aplus(self, raw) -> list[dict]:
        if not isinstance(raw, list):
            return []
        valid = {"headline", "grid", "compare", "story"}
        result = []
        for item in raw:
            if not isinstance(item, dict) or item.get("type") not in valid:
                continue
            items = [{str(k): str(v) for k, v in it.items()} for it in (item.get("items") or []) if isinstance(it, dict)]
            result.append({
                "type": item["type"],
                "title": str(item.get("title", "")),
                "text": str(item.get("text", "")),
                "items": items,
            })
        return result

    def _default_system(self) -> str:
        return (
            "你是千岸跨境上架平台的文案专家。严格按平台规则生成多语言 Listing 文案，"
            "零违规词、字符不超限、非直译、A10 埋词自然融标题。"
        )

    def _default_revise_system(self) -> str:
        return "你是合规修订专家。修复文案中的合规问题，只改文本字段，保留原意，输出完整 JSON。"

    def _banned_words_block(self, rules: dict) -> str:
        banned = rules.get("bannedWords", {})
        words = [w for group in banned.values() if isinstance(group, list) for w in group]
        return f"\n\n该平台禁用词（{', '.join(words[:25])}）" if words else ""

    def _lessons_block(self, platform: str) -> str:
        """记忆库召回（TODO：接入 memory_store）。"""
        return ""


__all__ = ["CopywritingSkill"]
