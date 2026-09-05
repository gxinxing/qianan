"""快照式评测用例集（Evals）。

两类用例：
1. 规则快照用例 —— 直接构造 PlatformListing + 平台规则，调用 ComplianceAgent，
   断言「输入 → 应产生的 issue 集合（field + severity + 关键 message 片段）」。
   不做多轮 Agent 模拟，直接构造中间状态，确定性可反复跑。
2. 历史事故用例（负面前置条件）—— 把 server/data/memory/experiences.jsonl 的
   教训编码成用例：构造一个「前置条件缺失」的 listing，断言合规引擎能抓到对应
   error。若引擎抓不到，该用例记 failed，note 写明「规则引擎缺口：XXX」——
   这正是评测集的价值，不允许为了让它通过而改产品代码。
"""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from PIL import Image

from app.agents.compliance import ComplianceAgent
from app.rules_store import load_rules
from app.schemas import ComplianceIssue, PlatformListing

CATEGORY = "home_kitchen"

# 单条用例函数返回值：(passed, got, skipped, note)
#   passed  断言是否成立
#   got     引擎实际产出的简短人类可读中文描述
#   skipped 用例跳过（如需要外网资源且无法 mock）
#   note    备注（历史事故用例在此写明引擎缺口）
CaseFn = Callable[[], Tuple[bool, str, bool, str]]


@dataclass
class Case:
    id: str
    name: str
    expect: str
    fn: CaseFn


@dataclass
class Suite:
    name: str
    desc: str
    cases: List[Case] = field(default_factory=list)


# ---------- 构造与断言辅助 ----------

def make_listing(
    platform: str,
    title: str = "",
    bullets: Optional[List[str]] = None,
    description: str = "",
    attributes: Optional[dict] = None,
    images: Optional[List[str]] = None,
    locales: Optional[List[str]] = None,
) -> PlatformListing:
    return PlatformListing(
        platform=platform,
        title=title,
        bullets=bullets or [],
        description=description,
        attributes=attributes or {},
        images=images or [],
        locales=locales or [],
    )


def run_compliance(
    listing: PlatformListing,
    platform: str,
    category: str = CATEGORY,
    rules: Optional[dict] = None,
) -> List[ComplianceIssue]:
    agent = ComplianceAgent()
    agent.run(listing, rules if rules is not None else load_rules(platform), category)
    return listing.compliance


def fmt_issues(issues: List[ComplianceIssue]) -> str:
    if not issues:
        return "0 个 issue（合规通过）"
    errs = sum(1 for i in issues if i.severity == "error")
    warns = len(issues) - errs
    detail = "；".join(f"[{i.severity}@{i.field}] {i.message}" for i in issues)
    return f"{errs} error / {warns} warn：{detail}"


def match(issues: List[ComplianceIssue], fld: str, severity: str, frag: str) -> bool:
    return any(
        i.field == fld and i.severity == severity and frag in i.message for i in issues
    )


def _png_data_uri(width: int, height: int, rgb: Tuple[int, int, int]) -> str:
    """本地构造主图（data URI），PIL 实测无需外网下载。"""
    im = Image.new("RGB", (width, height), rgb)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _title(n: int) -> str:
    """确定性生成 n 字符的无禁词标题。"""
    base = "Collapsible Silicone Food Storage Box Kitchen Organizer "
    return (base * (n // len(base) + 1))[:n]


# ---------- ① 长度类（length / length_each）----------

def _len_amazon_title_over() -> Tuple[bool, str, bool, str]:
    issues = run_compliance(make_listing("amazon", title=_title(201)), "amazon")
    ok = match(issues, "title", "error", "超出长度上限")
    return ok, fmt_issues(issues), False, ""


def _len_amazon_title_ok() -> Tuple[bool, str, bool, str]:
    issues = run_compliance(make_listing("amazon", title=_title(150)), "amazon")
    ok = not any(i.field == "title" and i.severity == "error" for i in issues)
    return ok, fmt_issues(issues), False, ""


def _len_amazon_bullet_over() -> Tuple[bool, str, bool, str]:
    long_bullet = "Durable silicone body with secure lid for daily use " * 10  # > 500
    issues = run_compliance(
        make_listing("amazon", title=_title(80), bullets=[long_bullet]), "amazon"
    )
    ok = match(issues, "bullets[0]", "error", "第 1 条超长")
    return ok, fmt_issues(issues), False, ""


def _len_amazon_bullets_ok() -> Tuple[bool, str, bool, str]:
    bullets = [("Durable silicone body with secure lid for daily use " * 6)[:500]] * 5
    issues = run_compliance(
        make_listing("amazon", title=_title(80), bullets=bullets), "amazon"
    )
    ok = not any(i.field.startswith("bullets[") and i.severity == "error" for i in issues)
    return ok, fmt_issues(issues), False, ""


def _len_shopee_desc_over() -> Tuple[bool, str, bool, str]:
    desc = "Premium silicone food storage box for family kitchen. " * 60  # > 3000
    issues = run_compliance(make_listing("shopee", description=desc), "shopee")
    ok = match(issues, "description", "error", "超出长度上限")
    return ok, fmt_issues(issues), False, ""


def _len_aliexpress_title_over() -> Tuple[bool, str, bool, str]:
    issues = run_compliance(make_listing("aliexpress", title=_title(129)), "aliexpress")
    ok = match(issues, "title", "error", "超出长度上限")
    return ok, fmt_issues(issues), False, ""


# ---------- ② 五点条数（count）----------

def _cnt_amazon_few() -> Tuple[bool, str, bool, str]:
    issues = run_compliance(
        make_listing("amazon", title=_title(80), bullets=["Point one.", "Point two.", "Point three."]),
        "amazon",
    )
    ok = match(issues, "bullets", "warn", "数量不足")
    return ok, fmt_issues(issues), False, ""


def _cnt_amazon_ok() -> Tuple[bool, str, bool, str]:
    bullets = ["Durable silicone body with secure lid."] * 5
    issues = run_compliance(
        make_listing("amazon", title=_title(80), bullets=bullets), "amazon"
    )
    ok = not any(i.field == "bullets" and i.severity == "warn" for i in issues)
    return ok, fmt_issues(issues), False, ""


# ---------- ③ 禁用词（banned_words）----------

def _bw_amazon_claims() -> Tuple[bool, str, bool, str]:
    issues = run_compliance(
        make_listing("amazon", title="The Best Seller Water Bottle 750ml for Sport"), "amazon"
    )
    ok = match(issues, "title", "error", "命中禁用词「best seller」")
    return ok, fmt_issues(issues), False, ""


def _bw_amazon_clean() -> Tuple[bool, str, bool, str]:
    issues = run_compliance(
        make_listing(
            "amazon",
            title=_title(80),
            bullets=["Silicone body with secure lid."],
            description="Collapsible food storage box for family kitchen.",
        ),
        "amazon",
    )
    ok = not any("命中禁用词" in i.message for i in issues)
    return ok, fmt_issues(issues), False, ""


def _bw_shopee_promo() -> Tuple[bool, str, bool, str]:
    issues = run_compliance(
        make_listing("shopee", title=_title(80), description="Limited time flash sale today only."), "shopee"
    )
    ok = match(issues, "description", "error", "命中禁用词「flash sale」")
    return ok, fmt_issues(issues), False, ""


def _bw_aliexpress_restricted() -> Tuple[bool, str, bool, str]:
    issues = run_compliance(
        make_listing("aliexpress", title="AAA Replica Watch Classic Style Gift"), "aliexpress"
    )
    ok = match(issues, "title", "error", "命中禁用词「replica」")
    return ok, fmt_issues(issues), False, ""


# ---------- ④ 必填类目属性（required_attrs）----------

def _attr_amazon_missing() -> Tuple[bool, str, bool, str]:
    issues = run_compliance(make_listing("amazon", title=_title(80)), "amazon")
    ok = match(issues, "attributes", "warn", "缺少必填类目属性")
    return ok, fmt_issues(issues), False, ""


def _attr_amazon_ok() -> Tuple[bool, str, bool, str]:
    rules = load_rules("amazon")
    attrs = {a: " silicone 750ml white CN" for a in rules["categoryAttributes"][CATEGORY]}
    issues = run_compliance(
        make_listing("amazon", title=_title(80), attributes=attrs), "amazon"
    )
    ok = not any(i.field == "attributes" for i in issues)
    return ok, fmt_issues(issues), False, ""


# ---------- ⑤ 必备段落（required_sections，lazada 真实启用该检查）----------

def _sec_lazada_missing() -> Tuple[bool, str, bool, str]:
    issues = run_compliance(
        make_listing("lazada", title=_title(80), description="Premium silicone box with secure lid."), "lazada"
    )
    ok = match(issues, "description", "warn", "缺少必备段落")
    return ok, fmt_issues(issues), False, ""


def _sec_lazada_ok() -> Tuple[bool, str, bool, str]:
    issues = run_compliance(
        make_listing(
            "lazada",
            title=_title(80),
            description="Premium silicone box. What's in the box: 1 x storage box, 1 x lid.",
        ),
        "lazada",
    )
    ok = not any("缺少必备段落" in i.message for i in issues)
    return ok, fmt_issues(issues), False, ""


# ---------- ⑥ 主图规格（image_spec，本地 data URI 构图，无需外网）----------

def _img_amazon_missing() -> Tuple[bool, str, bool, str]:
    issues = run_compliance(make_listing("amazon", title=_title(80)), "amazon")
    ok = match(issues, "mainImage", "warn", "未生成主图")
    return ok, fmt_issues(issues), False, ""


def _img_amazon_too_small() -> Tuple[bool, str, bool, str]:
    uri = _png_data_uri(500, 500, (255, 255, 255))
    issues = run_compliance(
        make_listing("amazon", title=_title(80), images=[uri]), "amazon"
    )
    ok = match(issues, "mainImage", "error", "主图尺寸不足")
    return ok, fmt_issues(issues), False, ""


def _img_amazon_colored_bg() -> Tuple[bool, str, bool, str]:
    uri = _png_data_uri(1600, 1600, (220, 60, 60))
    issues = run_compliance(
        make_listing("amazon", title=_title(80), images=[uri]), "amazon"
    )
    ok = match(issues, "mainImage", "error", "主图背景实测非纯白")
    return ok, fmt_issues(issues), False, ""


def _img_amazon_ok() -> Tuple[bool, str, bool, str]:
    uri = _png_data_uri(1600, 1600, (255, 255, 255))
    issues = run_compliance(
        make_listing("amazon", title=_title(80), images=[uri]), "amazon"
    )
    ok = match(issues, "mainImage", "warn", "白底通过") and not any(
        i.field == "mainImage" and i.severity == "error" for i in issues
    )
    return ok, fmt_issues(issues), False, ""


# ---------- ⑦ 语言覆盖（locale_coverage，shopee 多站点差异化）----------

def _loc_shopee_missing() -> Tuple[bool, str, bool, str]:
    issues = run_compliance(
        make_listing("shopee", title=_title(80), locales=["en-SG"]), "shopee"
    )
    ok = match(issues, "locales", "warn", "缺少语言覆盖")
    return ok, fmt_issues(issues), False, ""


def _loc_shopee_ok() -> Tuple[bool, str, bool, str]:
    issues = run_compliance(
        make_listing("shopee", title=_title(80), locales=["th-TH", "id-ID", "en-SG"]), "shopee"
    )
    ok = not any(i.field == "locales" for i in issues)
    return ok, fmt_issues(issues), False, ""


# ---------- ⑧ 平台差异化规则（同一输入在不同平台结论不同）----------

def _diff_amazon_title_130() -> Tuple[bool, str, bool, str]:
    issues = run_compliance(make_listing("amazon", title=_title(130)), "amazon")
    ok = not any(i.field == "title" and i.severity == "error" for i in issues)
    return ok, fmt_issues(issues), False, ""


def _diff_shopee_title_130() -> Tuple[bool, str, bool, str]:
    issues = run_compliance(make_listing("shopee", title=_title(130)), "shopee")
    ok = match(issues, "title", "error", "超出长度上限")
    return ok, fmt_issues(issues), False, ""


def _diff_aliexpress_title_130() -> Tuple[bool, str, bool, str]:
    issues = run_compliance(make_listing("aliexpress", title=_title(130)), "aliexpress")
    ok = match(issues, "title", "error", "超出长度上限")
    return ok, fmt_issues(issues), False, ""


def _diff_lazada_title_240() -> Tuple[bool, str, bool, str]:
    issues = run_compliance(make_listing("lazada", title=_title(240)), "lazada")
    ok = not any(i.field == "title" and i.severity == "error" for i in issues)
    return ok, fmt_issues(issues), False, ""


def _diff_sev_amazon_big_sale() -> Tuple[bool, str, bool, str]:
    issues = run_compliance(
        make_listing("amazon", title="Silicone Box Big Sale 2 Pack Set"), "amazon"
    )
    ok = match(issues, "title", "error", "命中禁用词「big sale」")
    return ok, fmt_issues(issues), False, ""


def _diff_sev_aliexpress_big_sale() -> Tuple[bool, str, bool, str]:
    issues = run_compliance(
        make_listing("aliexpress", title="Silicone Box Big Sale 2 Pack Set"), "aliexpress"
    )
    ok = match(issues, "title", "warn", "命中禁用词「big sale」")
    return ok, fmt_issues(issues), False, ""


# ---------- ⑨ 历史事故用例（负面前置条件，教训来自 experiences.jsonl）----------

def _incident(
    issues: List[ComplianceIssue], fld: str, gap_desc: str
) -> Tuple[bool, str, bool, str]:
    """教训要求引擎报 error；抓不到则记 failed + 引擎缺口说明。"""
    ok = any(i.severity == "error" and i.field == fld for i in issues)
    got = fmt_issues(issues)
    if ok:
        return True, got, False, ""
    return False, got, False, f"规则引擎缺口：{gap_desc}"


def _inc_amazon_stainless() -> Tuple[bool, str, bool, str]:
    """教训 8c8deb3aeb：材质未知时禁止宣称不锈钢等具体材质。"""
    listing = make_listing(
        "amazon",
        title="Soup Maker Blender 750ml for Home Kitchen",
        description="Made of premium stainless steel, durable and easy to clean.",
    )
    issues = run_compliance(listing, "amazon")
    return _incident(issues, "description", "attributes.material 为空时文案宣称具体材质（stainless steel），无「材质一致性」校验项")


def _inc_shopee_foodgrade() -> Tuple[bool, str, bool, str]:
    """教训 2555595206：材质仅标注 silicone 时应避免擅自宣称 food grade。"""
    listing = make_listing(
        "shopee",
        title="Silicone Food Storage Box 750ml",
        description="Food grade silicone storage box, safe for direct food contact.",
        attributes={"材质": "silicone"},
    )
    issues = run_compliance(listing, "shopee")
    return _incident(issues, "description", "材质档案仅为 silicone 却宣称 food grade，无「宣称与材质档案一致性」校验项")


def _inc_ali_leakproof() -> Tuple[bool, str, bool, str]:
    """教训 ac5d873d04：未验证防漏性能时，标题应避免 Leak Proof 等绝对化承诺。"""
    listing = make_listing(
        "aliexpress",
        title="Leak Proof Water Bottle 750ml Travel Mug",
        description="Portable bottle for daily use.",
    )
    issues = run_compliance(listing, "aliexpress")
    return _incident(issues, "title", "未验证防漏性能却在标题使用 Leak Proof 绝对化承诺，无「未验证性能宣称」校验项")


def _inc_tiktok_heat() -> Tuple[bool, str, bool, str]:
    """教训 9b976204ec：材质仅标注食品级硅胶时，不应编造具体耐温数值。"""
    listing = make_listing(
        "tiktokshop",
        title="Silicone Storage Box 750ml",
        description="耐温 -40℃ 至 230℃，可直接进烤箱使用。",
        attributes={"材质": "食品级硅胶"},
    )
    issues = run_compliance(listing, "tiktokshop")
    return _incident(issues, "description", "材质档案无耐温参数却编造具体耐温数值，无「量化参数与事实档案一致性」校验项")


def _inc_lazada_brand() -> Tuple[bool, str, bool, str]:
    """教训 1f1d3d750e：文案添加品牌词时应核实事实档案是否包含该品牌授权。"""
    listing = make_listing(
        "lazada",
        title="Portable Blender Bottle 500ml for Travel",
        description="Works with Ninja Foodi blender base, easy to carry.",
    )
    issues = run_compliance(listing, "lazada")
    return _incident(issues, "description", "文案使用第三方品牌词 Ninja 但事实档案无授权记录，无「品牌词授权校验」检查项")


def _inc_amazon_absolute() -> Tuple[bool, str, bool, str]:
    """教训 82561bbb59：绝对化极限词及虚假承诺应剔除（引擎应可抓到）。"""
    listing = make_listing(
        "amazon",
        title="The Best Seller Water Bottle Guaranteed Top Rated 750ml",
    )
    issues = run_compliance(listing, "amazon")
    ok = match(issues, "title", "error", "命中禁用词")
    return ok, fmt_issues(issues), False, ""


def _inc_amazon_vacuum() -> Tuple[bool, str, bool, str]:
    """教训 ae5a1eea08：未确认结构时禁止编造双层真空等工艺细节。"""
    listing = make_listing(
        "amazon",
        title="Insulated Travel Mug 500ml for Coffee",
        description="Double wall vacuum insulation keeps drinks cold for hours.",
    )
    issues = run_compliance(listing, "amazon")
    return _incident(issues, "description", "事实档案未确认结构却编造双层真空工艺细节，无「工艺描述与事实档案一致性」校验项")


def _inc_amazon_battery() -> Tuple[bool, str, bool, str]:
    """教训 8e7865f31b：电池续航未明确时，应避免宣称多次搅拌等具体性能。"""
    listing = make_listing(
        "amazon",
        title="Portable Electric Blender 500ml USB Rechargeable",
        description="Stirs up to 200 times per charge with long battery life.",
    )
    issues = run_compliance(listing, "amazon")
    return _incident(issues, "description", "电池续航未明确却宣称具体搅拌次数，无「量化性能宣称与事实档案一致性」校验项")


# ---------- 用例注册 ----------

SUITES: List[Suite] = [
    Suite(
        name="compliance_length",
        desc="字段长度上限（title / bullets 逐条 / description）",
        cases=[
            Case("len_amazon_001", "amazon 标题超 200 字符报 error", "1 个 error @field=title（超出长度上限）", _len_amazon_title_over),
            Case("len_amazon_002", "amazon 标题 150 字符不报错", "0 个 title 长度 error", _len_amazon_title_ok),
            Case("len_amazon_003", "amazon 五点单条超 500 字符报 error", "1 个 error @field=bullets[0]（第 1 条超长）", _len_amazon_bullet_over),
            Case("len_amazon_004", "amazon 五点每条 ≤500 字符不报错", "0 个 bullets 逐条长度 error", _len_amazon_bullets_ok),
            Case("len_shopee_001", "shopee 描述超 3000 字符报 error", "1 个 error @field=description（超出长度上限）", _len_shopee_desc_over),
            Case("len_aliexpress_001", "aliexpress 标题 129 字符报 error（上限 128）", "1 个 error @field=title（超出长度上限）", _len_aliexpress_title_over),
        ],
    ),
    Suite(
        name="compliance_bullets_count",
        desc="五点条数校验",
        cases=[
            Case("cnt_amazon_001", "amazon 五点仅 3 条报 warn（数量不足）", "1 个 warn @field=bullets（数量不足）", _cnt_amazon_few),
            Case("cnt_amazon_002", "amazon 五点 5 条不报条数 warn", "0 个 bullets 条数 warn", _cnt_amazon_ok),
        ],
    ),
    Suite(
        name="compliance_banned_words",
        desc="禁用词扫描（promotional / claims / restricted 分组）",
        cases=[
            Case("bw_amazon_001", "amazon 标题含 best seller 报 error（claims 组）", "1 个 error @field=title（命中禁用词）", _bw_amazon_claims),
            Case("bw_amazon_002", "amazon 全文案无禁用词不报错", "0 个禁用词 issue", _bw_amazon_clean),
            Case("bw_shopee_001", "shopee 描述含 flash sale 报 error（promotional 组）", "1 个 error @field=description（命中禁用词）", _bw_shopee_promo),
            Case("bw_aliexpress_001", "aliexpress 标题含 replica 报 error（restricted 组）", "1 个 error @field=title（命中禁用词）", _bw_aliexpress_restricted),
        ],
    ),
    Suite(
        name="compliance_required_attrs",
        desc="必填类目属性",
        cases=[
            Case("attr_amazon_001", "amazon home_kitchen 缺必填属性报 warn", "1 个 warn @field=attributes（缺少必填类目属性）", _attr_amazon_missing),
            Case("attr_amazon_002", "amazon 必填属性齐全不报错", "0 个 attributes issue", _attr_amazon_ok),
        ],
    ),
    Suite(
        name="compliance_required_sections",
        desc="必备段落（lazada 规则真实启用：What's in the box）",
        cases=[
            Case("sec_lazada_001", "lazada 描述缺 What's in the box 报 warn", "1 个 warn @field=description（缺少必备段落）", _sec_lazada_missing),
            Case("sec_lazada_002", "lazada 描述含 What's in the box 不报错", "0 个必备段落 issue", _sec_lazada_ok),
        ],
    ),
    Suite(
        name="compliance_image_spec",
        desc="主图规格（本地 data URI 构造图片，PIL 实测，无外网依赖）",
        cases=[
            Case("img_amazon_001", "amazon 无主图报 warn", "1 个 warn @field=mainImage（未生成主图）", _img_amazon_missing),
            Case("img_amazon_002", "amazon 主图 500×500 报 error（要求 ≥1000×1000）", "1 个 error @field=mainImage（主图尺寸不足）", _img_amazon_too_small),
            Case("img_amazon_003", "amazon 主图红色背景报 error（要求纯白）", "1 个 error @field=mainImage（背景非纯白）", _img_amazon_colored_bg),
            Case("img_amazon_004", "amazon 主图 1600×1600 纯白通过", "0 error + 1 warn @field=mainImage（白底通过）", _img_amazon_ok),
        ],
    ),
    Suite(
        name="compliance_locale_coverage",
        desc="语言覆盖（shopee 多站点）",
        cases=[
            Case("loc_shopee_001", "shopee 缺 th-TH/id-ID 语言报 warn", "1 个 warn @field=locales（缺少语言覆盖）", _loc_shopee_missing),
            Case("loc_shopee_002", "shopee 语言覆盖齐全不报错", "0 个 locales issue", _loc_shopee_ok),
        ],
    ),
    Suite(
        name="compliance_platform_diff",
        desc="平台差异化规则（同输入不同结论：标题上限 128/200/255、禁用词 severity 差异）",
        cases=[
            Case("diff_amazon_001", "130 字符标题在 amazon（上限 200）不报错", "0 个 title 长度 error", _diff_amazon_title_130),
            Case("diff_shopee_001", "130 字符标题在 shopee（上限 120）报 error", "1 个 error @field=title（超出长度上限）", _diff_shopee_title_130),
            Case("diff_aliexpress_001", "130 字符标题在 aliexpress（上限 128）报 error", "1 个 error @field=title（超出长度上限）", _diff_aliexpress_title_130),
            Case("diff_lazada_001", "240 字符标题在 lazada（上限 255）不报错", "0 个 title 长度 error", _diff_lazada_title_240),
            Case("diff_sev_amazon_001", "big sale 在 amazon 报 error", "1 个 error @field=title（命中禁用词）", _diff_sev_amazon_big_sale),
            Case("diff_sev_aliexpress_001", "big sale 在 aliexpress 仅报 warn", "1 个 warn @field=title（命中禁用词）", _diff_sev_aliexpress_big_sale),
        ],
    ),
    Suite(
        name="incidents_history",
        desc="历史事故用例（负面前置条件，教训来自 data/memory/experiences.jsonl）",
        cases=[
            Case("inc_amazon_stainless_001", "材质未知却宣称不锈钢应报 error（教训 8c8deb3aeb）", "1 个 error @field=description（材质宣称无依据）", _inc_amazon_stainless),
            Case("inc_shopee_foodgrade_001", "材质仅 silicone 却宣称 food grade 应报 error（教训 2555595206）", "1 个 error @field=description（宣称与材质档案不一致）", _inc_shopee_foodgrade),
            Case("inc_aliexpress_leakproof_001", "未验证防漏却在标题用 Leak Proof 应报 error（教训 ac5d873d04）", "1 个 error @field=title（未验证性能宣称）", _inc_ali_leakproof),
            Case("inc_tiktokshop_heat_001", "食品级硅胶却编造耐温数值应报 error（教训 9b976204ec）", "1 个 error @field=description（量化参数无事实依据）", _inc_tiktok_heat),
            Case("inc_lazada_brand_001", "文案使用未授权品牌词 Ninja 应报 error（教训 1f1d3d750e）", "1 个 error @field=description（品牌词无授权）", _inc_lazada_brand),
            Case("inc_amazon_absolute_001", "绝对化极限词 best seller/guaranteed 应被剔除（教训 82561bbb59）", "≥1 个 error @field=title（命中禁用词）", _inc_amazon_absolute),
            Case("inc_amazon_vacuum_001", "未确认结构却编造双层真空应报 error（教训 ae5a1eea08）", "1 个 error @field=description（工艺描述无事实依据）", _inc_amazon_vacuum),
            Case("inc_amazon_battery_001", "电池续航未明确却宣称搅拌次数应报 error（教训 8e7865f31b）", "1 个 error @field=description（量化性能无事实依据）", _inc_amazon_battery),
        ],
    ),
]
