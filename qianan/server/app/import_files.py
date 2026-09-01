"""平台后台导入文件生成 —— 对齐「后台上架」口径。

导出不再只是给人看的 JSON：每个平台附一份可导入卖家后台的 CSV
（核心列子集，utf-8-sig 编码，Excel 直接打开不乱码）。
- amazon：Flat File 风格（item-name / bullet-point1..5 / main-image-url …）
- shopee：Mass Upload 风格（Product Name / Description / Images …）
- 其余平台：通用导入表（title / description / images / 属性列）
"""
from __future__ import annotations

import csv
import io
import hashlib

from .schemas import PlatformListing


def _sku(product_name: str, platform: str) -> str:
    digest = hashlib.md5(product_name.encode("utf-8")).hexdigest()[:6].upper()
    return f"QA-{platform[:2].upper()}-{digest}"


def sku_for(product_name: str, platform: str) -> str:
    """对外公开：导入 CSV 与自动上架共用同一 SKU（同一商品身份贯穿导出与上架）。"""
    return _sku(product_name, platform)


def _to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def _amazon(product_name: str, l: PlatformListing) -> str:
    row = {
        "sku": _sku(product_name, "amazon"),
        "item-name": l.title,
        "brand": "Generic",
        "manufacturer": "QianAn Studio",
        "product-description": l.description,
        "main-image-url": l.images[0] if l.images else "",
        "other-image-url1": l.images[1] if len(l.images) > 1 else "",
        "item-type": l.attributes.get("category", "home-goods"),
        "target-audience": l.attributes.get("target_audience", "adults"),
    }
    for i in range(1, 6):
        row[f"bullet-point{i}"] = l.bullets[i - 1] if len(l.bullets) >= i else ""
    return _to_csv([row])


def _shopee(product_name: str, l: PlatformListing) -> str:
    row = {
        "Product Name": l.title,
        "Product Category": l.attributes.get("category", "Home & Living"),
        "Brand": "No Brand",
        "Description": l.description,
        "Images": ",".join(l.images),
        "Variation Name": "",
        "Stock": "100",
    }
    return _to_csv([row])


def _generic(product_name: str, l: PlatformListing) -> str:
    row = {
        "sku": _sku(product_name, l.platform),
        "title": l.title,
        "description": l.description,
        "images": " | ".join(l.images),
        **{f"attr_{k}": v for k, v in list(l.attributes.items())[:6]},
    }
    return _to_csv([row])


_BUILDERS = {"amazon": _amazon, "shopee": _shopee}


def build_import_files(product_name: str, listing: PlatformListing) -> dict[str, str]:
    """返回 {文件名: csv 内容}，前端可一键下载。"""
    builder = _BUILDERS.get(listing.platform, _generic)
    filename = f"{listing.platform}_import_{_sku(product_name, listing.platform)}.csv"
    return {filename: builder(product_name, listing)}
