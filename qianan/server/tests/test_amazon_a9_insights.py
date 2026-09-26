"""验证 Amazon A9 埋词优化与竞品痛点反切机制。"""
from app.agents.copywriting import CopywritingAgent
from app.agents.insights import format_complaints_brief, get_category_complaints
from app.bailian.client import MockBailianClient
from app.import_files import build_import_files
from app.rules_store import load_rules
from app.schemas import GenerateRequest, Understanding


def test_category_complaints_retrieval():
    complaints = get_category_complaints("home_kitchen")
    assert len(complaints) >= 3
    tags = [c["counter_tag"] for c in complaints]
    assert "LEAK-PROOF ASSURANCE" in tags

    brief = format_complaints_brief("home_kitchen")
    assert "LEAK-PROOF ASSURANCE" in brief
    assert "竞品常见痛点" in brief


def test_amazon_copywriting_mock_generates_a9_terms_and_pain_points():
    client = MockBailianClient()
    agent = CopywritingAgent(client)

    req = GenerateRequest(
        product_name="便携式榨汁杯",
        selling_points="双层硅胶密封防漏，强劲纯铜动力碎冰，全机身可拆洗",
        category="home_kitchen",
        platforms=["amazon"],
    )
    understanding = Understanding(
        category="home_kitchen",
        product_type="portable blender cup",
        selling_points=["双层硅胶密封防漏", "强劲纯铜动力碎冰", "全机身可拆洗"],
        keywords=["blender", "smoothie", "portable mixer"],
        attributes={"容量": "380ml", "材质": "Tritan"},
    )

    rules = load_rules("amazon")
    listing = agent._mock(req, understanding, "amazon", rules, ["en-US"])

    # 1. 验证五点描述具备竞品痛点反切大写标签
    assert len(listing.bullets) == 5
    assert listing.bullets[0].startswith("[LEAK-PROOF ASSURANCE]")

    # 2. 验证痛点反切映射表
    assert len(listing.pain_point_mapping) >= 2
    assert listing.pain_point_mapping[0]["bullet_tag"] == "LEAK-PROOF ASSURANCE"

    # 3. 验证 Amazon A9 Search Terms 规范
    assert listing.search_terms
    terms_bytes = len(listing.search_terms.encode("utf-8"))
    assert terms_bytes <= 249
    assert listing.search_terms == listing.search_terms.lower()
    assert "," not in listing.search_terms
    assert ";" not in listing.search_terms

    # 4. 验证 Flat File CSV 包含 generic-keywords 列
    import_files = build_import_files(req.product_name, listing)
    csv_key = next(k for k in import_files if k.startswith("amazon_import"))
    csv_content = import_files[csv_key]
    assert "generic-keywords" in csv_content
    assert listing.search_terms in csv_content
