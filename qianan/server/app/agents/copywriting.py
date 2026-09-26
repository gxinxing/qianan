"""③ 文案 Agent：Qwen-Max 按平台规则生成多语言 Listing 文案。

每个平台一次调用，要求模型返回覆盖全部目标语言的 JSON；
Mock 模式下本地拼装确定性文案（遵守长度规则，保证合规检查能过）。
系统提示词走 prompt_store 版本化加载（进化提案经人审后可热更新、可回滚）。
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from .. import prompt_store
from ..bailian.client import TEXT_MODEL, BailianLike
from ..schemas import AplusModule, GenerateRequest, PlatformListing, Understanding
from .insights import format_complaints_brief, get_category_complaints
from .preflight import build_preflight_report
from .rules_engine import RulesEngineAgent


class CopywritingAgent:
    def __init__(self, client: BailianLike) -> None:
        self.client = client

    async def run(
        self,
        req: GenerateRequest,
        understanding: Understanding,
        platform: str,
        rules: dict,
        focus: str = "",
        memories: list | None = None,
    ) -> PlatformListing:
        locales: list[str] = rules.get("locales", ["en-US"])
        if self.client.is_mock:
            return self._mock(req, understanding, platform, rules, locales)

        category = understanding.category or req.category or "home_kitchen"
        complaints_brief = format_complaints_brief(category)

        amazon_extra_prompt = ""
        amazon_extra_schema = ""
        if platform == "amazon":
            amazon_extra_prompt = f"""
{complaints_brief}

【Amazon A9/COSMO 搜索算法与操盘要求】：
1. 标题结构（Formula）：[Brand] + [Core Seed Keyword] + [Differentiator] + [Specs/Material] + [Use Case/Audience]。
   - 核心大词置于前 80 字符（确保移动端截断前展示）；各词首字母大写（Title Case）；禁止符号乱用与空洞自夸。
2. 五点描述（Bullets）：严格 5 条，全部使用大写方括号标签开头（如 [LEAK-PROOF DESIGN]、[POWERFUL 20000RPM]）；前 3 条必须精准反切上述竞品常见痛点。
3. 后台搜索词（search_terms / Generic Keywords）：
   - 严格 ≤249 字节（UTF-8），纯小写，空格分隔，无逗号标点。
   - 包含高频搜索长尾词、别名、同义词，严禁重复标题与五点已包含的词，严禁包含竞品品牌词。
4. 竞品防御对照（pain_point_mapping）：列出针对的前 2-3 个核心差评痛点及解决特性。
"""
            amazon_extra_schema = """,
  "search_terms": "仅 Amazon 需要：≤249 字节纯小写空格分隔后台关键词",
  "pain_point_mapping": [
    {"complaint": "竞品差评痛点", "counter_feature": "本品反击设计与解决特性", "bullet_tag": "对应五点标签"}
  ],
  "keyword_strategy": {
    "core_seed": "核心大词",
    "differentiator": "差异化卖点词",
    "target_audience_kw": "目标客群/场景词"
  }"""

        user_prompt = f"""为以下商品生成 {rules['displayName']} 平台上架文案。

商品理解（JSON）：
{understanding.model_dump_json(ensure_ascii=False)}

平台规则约束：
{RulesEngineAgent.constraint_brief(rules)}
{amazon_extra_prompt}
输出严格 JSON：
{{
  "locales": {json.dumps(locales)},
  "title": {{ "<locale>": "本地化标题" }},
  "bullets": ["五点描述（仅 Amazon 需要，其他平台给空数组）"],
  "description": {{ "<locale>": "本地化描述" }},
  "attributes": {{ "属性名": "值" }},
  "aplus": [
    {{"type": "headline", "title": "详情页首屏横幅主标题（短句，有冲击力）", "text": "副标题（1 句）"}},
    {{"type": "grid", "title": "卖点区块标题", "items": [
      {{"title": "卖点小标题", "text": "一行说明"}},
      {{"title": "卖点小标题", "text": "一行说明"}},
      {{"title": "卖点小标题", "text": "一行说明"}}
    ]}},
    {{"type": "compare", "title": "规格参数", "items": [
      {{"label": "参数名", "value": "参数值"}}
    ]}},
    {{"type": "story", "title": "品牌故事标题", "text": "2-3 句品牌故事，温暖可信，不夸大"}}
  ]{amazon_extra_schema}
}}
目标语言：{', '.join(locales)}。标题与描述必须遵守字符上限，禁止出现规则中的禁用词。
aplus 全部内容用第一目标语言（{locales[0] if locales else 'en-US'}）撰写，面向转化，具体可信，避免空泛形容词。{("生成要点（调度 Agent 规划）：" + focus) if focus else ""}{_memory_block(memories)}"""

        system = prompt_store.load("copywriting_system")
        raw = await asyncio.to_thread(self.client.chat, system, user_prompt, TEXT_MODEL)
        data = await _chat_json(self.client, system, user_prompt, raw)
        return _to_listing(platform, rules, locales, data)

    async def revise(
        self, listing: PlatformListing, rules: dict, errors: list
    ) -> PlatformListing:
        """合规自愈：按体检出的 error 修订文案，只改文本字段，图片等继承原稿。"""
        if self.client.is_mock:
            return self._revise_local(listing, rules)

        issues_text = "\n".join(f"- 字段 {i.field}：{i.message}" for i in errors)
        user_prompt = f"""修订 {rules.get('displayName', listing.platform)} 平台的上架文案。

当前文案（JSON，title/description 为 {listing.locales[0] if listing.locales else 'en-US'} 语言）：
{json.dumps({
    'title': listing.title,
    'bullets': listing.bullets,
    'description': listing.description,
    'attributes': listing.attributes,
    'aplus': [m.model_dump() for m in listing.aplus],
}, ensure_ascii=False)}

合规体检反馈（必须全部修复）：
{issues_text}

平台规则约束：
{RulesEngineAgent.constraint_brief(rules)}

输出修订后的完整 JSON（与输入同结构：title / bullets / description / attributes / aplus）。"""
        system = prompt_store.load("copywriting_revise_system")
        raw = await asyncio.to_thread(self.client.chat, system, user_prompt, TEXT_MODEL)
        data = await _chat_json(self.client, system, user_prompt, raw)

        revised = listing.model_copy(deep=True)
        revised.title = str(data.get("title") or listing.title)
        if isinstance(data.get("bullets"), list):
            revised.bullets = [str(b) for b in data["bullets"]]
        if isinstance(data.get("description"), str) and data["description"]:
            revised.description = data["description"]
        if isinstance(data.get("attributes"), dict):
            revised.attributes = {str(k): str(v) for k, v in data["attributes"].items()}
        aplus = _to_aplus(data.get("aplus"))
        if aplus:
            revised.aplus = aplus
        if data.get("search_terms"):
            revised.search_terms = str(data["search_terms"]).strip()
        if isinstance(data.get("pain_point_mapping"), list):
            revised.pain_point_mapping = data["pain_point_mapping"]
        if isinstance(data.get("keyword_strategy"), dict):
            revised.keyword_strategy = data["keyword_strategy"]
        return revised

    def _revise_local(self, listing: PlatformListing, rules: dict) -> PlatformListing:
        """Mock 自愈：剔除禁用词 + 按规则截断超长字段。"""
        import re as _re

        banned = [
            w
            for words in (rules.get("bannedWords") or {}).values()
            if isinstance(words, list)  # 排除 restrictedNote 等非列表字段
            for w in words or []
        ]

        def clean(text: str) -> str:
            for word in banned:
                text = _re.sub(rf"(?<![a-z0-9]){_re.escape(word)}(?![a-z0-9])", "", text, flags=_re.IGNORECASE)
            return _re.sub(r"\s{2,}", " ", text).strip(" -·|")

        title_limit = int(rules.get("title", {}).get("maxLength", 0))
        desc_limit = int(rules.get("description", {}).get("maxLength", 0))
        bullet_limit = int(rules.get("bullets", {}).get("maxLengthPer", 0))

        def cap(text: str, limit: int) -> str:
            return text if not limit or len(text) <= limit else text[: limit - 1].rstrip() + "…"

        revised = listing.model_copy(deep=True)
        revised.title = cap(clean(revised.title), title_limit)
        revised.bullets = [cap(clean(b), bullet_limit) for b in revised.bullets]
        revised.description = cap(clean(revised.description), desc_limit)
        for m in revised.aplus:
            m.title, m.text = cap(clean(m.title), title_limit), cap(clean(m.text), desc_limit)
            for it in m.items:
                for k in list(it.keys()):
                    it[k] = cap(clean(it[k]), desc_limit)
        return revised

    def _mock(
        self, req: GenerateRequest, u: Understanding, platform: str, rules: dict, locales: list[str]
    ) -> PlatformListing:
        kw = u.keywords or [req.product_name]
        base_title = f"{u.product_type or req.product_name} - {', '.join(u.selling_points[:2]) or 'premium quality'}"
        title: dict[str, str] = {}
        description: dict[str, str] = {}
        for i, locale in enumerate(locales):
            lang = locale.split("-")[0]
            t = base_title if lang == "en" else f"[{lang}] {base_title}"
            title[locale] = t[: int(rules.get("title", {}).get("maxLength", 200))]
            d = " | ".join(u.selling_points) or req.selling_points
            description[locale] = (f"{t}. " + d)[: int(rules.get("description", {}).get("maxLength", 2000))]
        bullets: list[str] = []
        search_terms = ""
        pain_point_mapping: list[dict[str, str]] = []
        keyword_strategy: dict[str, Any] = {}

        if rules.get("bullets"):
            count = rules["bullets"].get("count", 5)
            per = rules["bullets"].get("maxLengthPer", 500)
            pool = u.selling_points or [req.selling_points]
            if platform == "amazon":
                complaints = get_category_complaints(u.category or req.category)[:3]
                for i in range(count):
                    if i < len(complaints):
                        c = complaints[i]
                        b_text = f"[{c['counter_tag']}] {c['suggested_antidote']} - Engineered to solve {c['complaint'][:12]}."
                        bullets.append(b_text[:per])
                        pain_point_mapping.append({
                            "complaint": c["complaint"],
                            "counter_feature": c["suggested_antidote"],
                            "bullet_tag": c["counter_tag"],
                        })
                    else:
                        b_text = f"[{kw[i % len(kw)].upper()}] {pool[i % len(pool)]} - Designed for everyday reliability."
                        bullets.append(b_text[:per])

                # 构造符合 A9 规范的后台关键词（≤249 字节，去重小写空格隔开）
                seed_terms = [
                    f"{w.lower()} accessory" for w in kw[:3]
                ] + ["portable lightweight", "everyday essentials", "travel compact", "quick setup", "durable quality"]
                raw_st = " ".join(dict.fromkeys(seed_terms))
                while len(raw_st.encode("utf-8")) > 249 and " " in raw_st:
                    raw_st = raw_st.rsplit(" ", 1)[0]
                search_terms = raw_st[:249]
                keyword_strategy = {
                    "core_seed": kw[0] if kw else req.product_name,
                    "differentiator": u.selling_points[0] if u.selling_points else "High Performance",
                    "target_audience_kw": u.target_audience or "Daily Users",
                }
            else:
                bullets = [f"{kw[i % len(kw)].title()} - {pool[i % len(pool)]}"[:per] for i in range(count)]
        attrs = {k: (v or "TBD") for k, v in (u.attributes or {}).items()}
        aplus = [
            AplusModule(
                type="headline",
                title=(u.product_type or req.product_name).title(),
                text="Thoughtfully designed for everyday life.",
            ),
            AplusModule(
                type="grid",
                title="Why you'll love it",
                items=[
                    {"title": kw[i % len(kw)].title(), "text": (u.selling_points or [req.selling_points])[i]}
                    for i in range(min(3, len(u.selling_points or [req.selling_points])))
                ],
            ),
            AplusModule(
                type="compare",
                title="Specifications",
                items=[{"label": k, "value": v} for k, v in list(attrs.items())[:6]],
            ),
            AplusModule(
                type="story",
                title="Our Promise",
                text="We design practical products that make daily routines a little easier, and stand behind every order.",
            ),
        ]
        listing = PlatformListing(
            platform=platform,
            display_name=rules.get("displayName", platform),
            locales=locales,
            title=title.get(locales[0], ""),
            bullets=bullets,
            description=description.get(locales[0], ""),
            attributes=attrs,
            aplus=aplus,
            search_terms=search_terms,
            pain_point_mapping=pain_point_mapping,
            keyword_strategy=keyword_strategy,
        )
        listing.preflight_report = build_preflight_report(listing, rules)
        return listing


def _memory_block(memories: list | None) -> str:
    """把记忆库召回的教训渲染成提示词段落（无记忆时为空串）。"""
    if not memories:
        return ""
    lines = "\n".join(f"- {str(m.get('lesson', ''))[:40]}" for m in memories[:3])
    return f"\n\n过往教训（来自历史自愈经验，务必遵守以免重蹈覆辙）：\n{lines}"


def _to_listing(platform: str, rules: dict, locales: list[str], data: dict) -> PlatformListing:
    titles = data.get("title") or {}
    descs = data.get("description") or {}
    first = locales[0] if locales else "en-US"
    title = titles.get(first) or (titles.get("value") if isinstance(titles, dict) else "") or str(titles)
    desc = descs.get(first) or ""
    if isinstance(descs, str):
        desc = descs

    search_terms = str(data.get("search_terms") or "").strip().lower()
    if search_terms:
        # A9 249 字节硬限制安全截断
        while len(search_terms.encode("utf-8")) > 249 and " " in search_terms:
            search_terms = search_terms.rsplit(" ", 1)[0]
        if len(search_terms.encode("utf-8")) > 249:
            search_terms = search_terms.encode("utf-8")[:249].decode("utf-8", errors="ignore")

    pain_point_mapping = [
        {str(k): str(v) for k, v in item.items()}
        for item in (data.get("pain_point_mapping") or [])
        if isinstance(item, dict)
    ]
    keyword_strategy = data.get("keyword_strategy") if isinstance(data.get("keyword_strategy"), dict) else None

    listing = PlatformListing(
        platform=platform,
        display_name=rules.get("displayName", platform),
        locales=locales,
        title=str(title),
        bullets=list(data.get("bullets") or []),
        description=str(desc),
        attributes=dict(data.get("attributes") or {}),
        aplus=_to_aplus(data.get("aplus")),
        search_terms=search_terms,
        pain_point_mapping=pain_point_mapping,
        keyword_strategy=keyword_strategy,
    )
    listing.preflight_report = build_preflight_report(listing, rules)
    return listing


def _to_aplus(raw) -> list[AplusModule]:
    """解析模型返回的 A+ 模块，容忍缺字段与非法 type。"""
    if not isinstance(raw, list):
        return []
    valid = {"headline", "grid", "compare", "story"}
    modules: list[AplusModule] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        mtype = item.get("type") if item.get("type") in valid else None
        if not mtype:
            continue
        items = [
            {str(k): str(v) for k, v in it.items()}
            for it in (item.get("items") or [])
            if isinstance(it, dict)
        ]
        modules.append(
            AplusModule(
                type=mtype,
                title=str(item.get("title") or ""),
                text=str(item.get("text") or ""),
                items=items,
            )
        )
    return modules


async def _chat_json(client: BailianLike, system: str, prompt: str, raw: str) -> dict:
    """解析模型 JSON 输出；失败时把错误反馈给模型重试一次（自愈）。"""
    for attempt in range(2):
        try:
            return _extract_json(raw)
        except (json.JSONDecodeError, ValueError):
            if attempt:
                raise
            raw = await asyncio.to_thread(
                client.chat,
                system,
                f"{prompt}\n\n注意：你上一次输出的 JSON 解析失败。常见问题：键未加双引号、尾随逗号、"
                f"包含 markdown 代码块。\n失败输出：{raw[:600]}\n\n请重新输出完整合法的 JSON"
                f"（不允许 markdown 代码块，键必须双引号，无尾随逗号）。",
                TEXT_MODEL,
            )
    raise ValueError(f"文案输出无法解析: {raw[:200]}")  # pragma: no cover


def _extract_json(text: str) -> dict:
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
