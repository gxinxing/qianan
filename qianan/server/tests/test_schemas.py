"""数据模型（app/schemas.py）纯逻辑测试：默认值与字段上限的边界校验。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import ALL_PLATFORMS, GenerateRequest, PlatformListing


def test_generate_request_defaults_limits_and_listing_defaults():
    """GenerateRequest：默认 platforms=全平台，三个 max_length 边界越界即拒；PlatformListing 默认合规通过。"""
    default = GenerateRequest()
    assert default.platforms == list(ALL_PLATFORMS)
    assert default.platforms == ["amazon", "shopee", "aliexpress", "lazada", "tiktokshop"]
    assert default.category == "home_kitchen"

    ok = GenerateRequest(product_name="不锈钢厨刀", selling_points="锋利耐用", platforms=["amazon"])
    assert ok.platforms == ["amazon"]

    with pytest.raises(ValidationError):  # product_name 上限 200
        GenerateRequest(product_name="x" * 201)
    with pytest.raises(ValidationError):  # selling_points 上限 2000
        GenerateRequest(selling_points="x" * 2001)
    with pytest.raises(ValidationError):  # platforms 上限 10 个
        GenerateRequest(platforms=[f"p{i}" for i in range(11)])

    listing = PlatformListing(platform="shopee")
    assert listing.compliance == []  # 合规问题列表由 ComplianceAgent 回填
    assert listing.compliance_passed is True
    assert listing.bullets == []
    assert listing.attributes == {}
