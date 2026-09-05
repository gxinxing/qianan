"""合规体检 Agent（app/agents/compliance.py）确定性校验测试。

全部用构造数据：不触网（主图仅用空 / mock:// 占位），验证 error/warn 分级
与 compliance_passed 的门禁语义 —— error 拦截、warn 仅提示。
"""
from __future__ import annotations

from app.agents.compliance import ComplianceAgent
from app.rules_store import load_rules
from app.schemas import PlatformListing


def _check(platform: str, listing: PlatformListing, category: str = "home_kitchen") -> PlatformListing:
    """跑一遍合规体检并返回被回填的 listing（ComplianceAgent.run 原地写 compliance）。"""
    ComplianceAgent().run(listing, load_rules(platform), category)
    return listing


def _issues(listing: PlatformListing, check_id: str) -> list:
    return [i for i in listing.compliance if i.check_id == check_id]


def test_title_length_boundary_200_passes_and_201_fails():
    """标题压线 200 字符通过；201 字符触发 amz-title-001（error）并置不通过。"""
    at_limit = _check("amazon", PlatformListing(platform="amazon", title="x" * 200, bullets=["b"] * 5))
    assert not _issues(at_limit, "amz-title-001")
    assert at_limit.compliance_passed

    over = _check("amazon", PlatformListing(platform="amazon", title="x" * 201, bullets=["b"] * 5))
    issues = _issues(over, "amz-title-001")
    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert issues[0].field == "title"
    assert not over.compliance_passed


def test_banned_words_hit_and_whole_word_boundary():
    """claims 组禁词按整词命中（error）；嵌在长单词内的子串不误报。"""
    hit = _check("amazon", PlatformListing(platform="amazon", title="The Best kitchen knife", bullets=["b"] * 5))
    issues = _issues(hit, "amz-title-002")
    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert "best" in issues[0].message
    assert not hit.compliance_passed

    # “Bestseller”内含 best 但不是独立整词 → 不应命中（前后缀字符拦截）
    no_hit = _check(
        "amazon",
        PlatformListing(platform="amazon", title="Bestseller kitchen gadget", bullets=["b"] * 5),
    )
    assert not _issues(no_hit, "amz-title-002")


def test_bullets_count_and_per_item_length():
    """五点描述：数量不足 4<5 → error；单条 501>500 → error 且定位到 bullets[1]；压线 5×500 全过。"""
    too_few = _check("amazon", PlatformListing(platform="amazon", title="ok", bullets=["b"] * 4))
    issues = _issues(too_few, "amz-bullet-001")
    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert not too_few.compliance_passed

    overlong = _check(
        "amazon",
        PlatformListing(platform="amazon", title="ok", bullets=["b" * 500, "b" * 501, "b", "b", "b"]),
    )
    issues = _issues(overlong, "amz-bullet-002")
    assert [i.field for i in issues] == ["bullets[1]"]
    assert issues[0].severity == "error"

    at_limit = _check("amazon", PlatformListing(platform="amazon", title="ok", bullets=["b" * 500] * 5))
    assert not [i for i in at_limit.compliance if i.check_id.startswith("amz-bullet")]


def test_warn_does_not_block_error_does_and_image_placeholders_offline():
    """warn 级（缺属性/无主图/描述超长/主图占位）只提示不拦截；error 级置 compliance_passed=False。

    主图只出现空列表与 mock:// 占位两种形态，保证零网络请求。
    """
    warn_only = _check("amazon", PlatformListing(platform="amazon", title="ok title", bullets=["b"] * 5))
    assert warn_only.compliance, "构造的 listing 应至少命中缺属性/无主图两类 warn"
    assert {i.severity for i in warn_only.compliance} == {"warn"}
    assert "品牌" in _issues(warn_only, "amz-attr-001")[0].message  # home_kitchen 必填属性示例
    assert "未生成主图" in _issues(warn_only, "amz-img-001")[0].message
    assert warn_only.compliance_passed

    # 描述超 3000：amz-desc-001 规则声明 severity=warn，同样不拦截
    long_desc = _check(
        "amazon",
        PlatformListing(platform="amazon", title="ok", bullets=["b"] * 5, description="x" * 3001),
    )
    desc = _issues(long_desc, "amz-desc-001")
    assert desc and desc[0].severity == "warn"
    assert long_desc.compliance_passed

    # mock:// 占位主图：跳过规范实测，仅 warn 提示
    mock_img = _check(
        "amazon",
        PlatformListing(platform="amazon", title="ok", bullets=["b"] * 5, images=["mock://generated"]),
    )
    img = _issues(mock_img, "amz-img-001")
    assert img and img[0].severity == "warn"
    assert "Mock" in img[0].message
    assert mock_img.compliance_passed

    # 标题命中 claims 禁词 → error → 拦截
    error_case = _check(
        "amazon",
        PlatformListing(platform="amazon", title="miracle cure gadget", bullets=["b"] * 5),
    )
    assert not error_case.compliance_passed


def test_shopee_required_sections_and_locale_coverage():
    """Shopee 专属检查：描述缺必备段落 → warn；locales 覆盖不足 → warn；补齐后消除。"""
    sparse = _check(
        "shopee",
        PlatformListing(platform="shopee", title="ok", description="only a short intro", locales=["th-TH"]),
    )
    sections = _issues(sparse, "shp-desc-002")
    assert sections and sections[0].severity == "warn"
    assert "产品介绍" in sections[0].message
    locale = _issues(sparse, "shp-locale-001")
    assert locale and locale[0].field == "locales"
    assert "id-ID" in locale[0].message

    fixed = _check(
        "shopee",
        PlatformListing(
            platform="shopee",
            title="ok",
            description="【产品介绍】优质厨具。【规格参数】食品级不锈钢。",
            locales=["th-TH", "id-ID", "vi-VN"],
        ),
    )
    assert not _issues(fixed, "shp-desc-002")
    assert not _issues(fixed, "shp-locale-001")
