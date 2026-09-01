"""MockBrowserPublisher：Playwright 驱动 mock 卖家后台（演示主路径）。

流程：打开页面 → 按 data-sc-field 协议填表 → 注入主图 → 点击提交 →
等待 live 视图 → 回传 live_url 与 listing_id。每步截图留痕。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from ..schemas import PublishStep
from .base import BasePublisher, PublishResult

logger = logging.getLogger(__name__)

# mock 页面由 FastAPI 直接伺服（/mock/seller-central），上架链路只依赖本服务
DEFAULT_PAGE_URL = "http://localhost:8001/mock/seller-central"


class MockBrowserPublisher(BasePublisher):
    name = "mock_browser"

    def __init__(self, headless: bool = True, page_url: str | None = None):
        self.headless = headless
        self.page_url = page_url or os.environ.get("MOCK_PAGE_URL", DEFAULT_PAGE_URL)

    async def publish(self, listing: dict, job_dir: Path) -> PublishResult:
        from playwright.async_api import async_playwright

        steps: list[PublishStep] = []
        shots = job_dir / "shots"
        shots.mkdir(parents=True, exist_ok=True)

        async def shot(page, name: str) -> str:
            path = shots / f"{len(steps) + 1:02d}_{name}.png"
            await page.screenshot(path=str(path))
            return path.name  # 只存文件名，API 层拼下载路径

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=self.headless)
                page = await browser.new_page(viewport={"width": 1280, "height": 960})
                try:
                    await page.goto(self.page_url, wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_selector("#btn-save", timeout=10000)
                    steps.append(
                        PublishStep(action="open_page", detail=f"打开卖家后台 {self.page_url}", screenshot=await shot(page, "open"))
                    )

                    attrs = listing.get("attributes") or {}
                    fields = {
                        "title": listing.get("title", ""),
                        "brand": listing.get("brand") or attrs.get("brand") or "Generic",
                        "sku": listing.get("sku", ""),
                        "description": listing.get("description", ""),
                        # mock 平台演示价：上架包未含价格字段时的占位
                        "price": str(attrs.get("price") or "19.99"),
                        "quantity": str(attrs.get("quantity") or "100"),
                    }
                    for i, bullet in enumerate((listing.get("bullets") or [])[:5], 1):
                        fields[f"bullet{i}"] = bullet
                    for key, value in fields.items():
                        if value:
                            await page.fill(f'[data-sc-field="{key}"]', str(value))
                    steps.append(
                        PublishStep(
                            action="fill_fields",
                            detail=f"按 data-sc-field 协议填充 {sum(1 for v in fields.values() if v)} 个字段",
                            screenshot=await shot(page, "filled"),
                        )
                    )

                    images = listing.get("images") or []
                    if images:
                        await page.evaluate(
                            "(src) => { document.getElementById('img-box').innerHTML = '<img src=\"' + src + '\" alt=\"main image\" />'; }",
                            images[0],
                        )
                        steps.append(
                            PublishStep(action="upload_image", detail="上传主图", screenshot=await shot(page, "image"))
                        )

                    await page.click("#btn-save")
                    await page.wait_for_selector("#live-view:not([hidden])", timeout=20000)
                    id_text = (await page.text_content("#live-listing-id") or "").strip()
                    listing_id = id_text.split("·")[0].strip()
                    steps.append(
                        PublishStep(action="submit", detail="点击 Save and Finish，平台受理", screenshot=await shot(page, "submitted"))
                    )
                    steps.append(
                        PublishStep(
                            action="live_confirm",
                            detail=f"listing 已上线：{listing_id}",
                            screenshot=await shot(page, "live"),
                        )
                    )
                    return PublishResult(ok=True, live_url=page.url, listing_id=listing_id, steps=steps)
                finally:
                    await browser.close()
        except Exception as exc:  # noqa: BLE001 —— 失败也要带回已留痕的 steps
            logger.exception("mock 上架执行失败")
            return PublishResult(ok=False, error=str(exc), steps=steps)
