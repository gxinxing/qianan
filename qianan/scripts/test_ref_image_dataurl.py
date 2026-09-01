"""以图改图 data URL 链路实测脚本。

模拟前端上传的真实路径：
1. 文生图先产出一张"商品照片"（或用本地图片）
2. 下载 → base64 → data:image/jpeg;base64,...（= 前端 FileReader.readAsDataURL 产物）
3. 调 BailianClient.image_gen(prompt, ref_image=data_url) 以图改图
4. 打印结果图 URL

用法：/usr/bin/python3 scripts/test_ref_image_dataurl.py
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

import requests  # noqa: E402

from app.bailian.client import BailianClient  # noqa: E402

REF_PROMPT = (
    "Reference image 1 (图1) is the real product photo. Keep the exact same product "
    "(shape, color, pattern, material, every detail) — do NOT redesign or reimagine it. "
    "基于这张真实商品照生成电商主图：平台主图规范：纯白背景，画面不含文字，无水印。"
    "要求：保持商品本体与照片完全一致，仅把背景改成纯白；电商级布光，主体居中占画面 85% 以上，商业摄影质感。"
)


def main() -> None:
    client = BailianClient()

    # 1) 先生成一张商品照（大豆蜡香薰蜡烛，样例商品之一）
    print("[1/4] 文生图产出商品照 …", flush=True)
    photo_url = client.image_gen(
        "电商商品摄影：一只琥珀色玻璃罐装大豆蜡香薰蜡烛，木盖，米色标签，"
        "放在浅木桌面上，旁边有一小束干花，暖色调自然光，浅景深，商业摄影质感。"
    )
    print("      商品照:", photo_url, flush=True)

    # 2) 下载 → base64 data URL（完全复刻前端上传形态）
    print("[2/4] 下载并转 base64 data URL …", flush=True)
    raw = requests.get(photo_url, timeout=60).content
    data_url = "data:image/png;base64," + base64.b64encode(raw).decode()
    print(f"      data URL 大小: {len(data_url) / 1024:.0f} KB", flush=True)

    # 3) data URL 参考图 → 以图改图
    print("[3/4] 以图改图（data URL 参考图）…", flush=True)
    edited_url = client.image_gen(REF_PROMPT, ref_image=data_url)
    print("      SUCCESS:", edited_url, flush=True)

    # 4) 顺手对比：同 prompt 用原始 https URL 作参考图
    print("[4/4] 对照组：同 prompt 用 https URL 参考图 …", flush=True)
    try:
        edited_url2 = client.image_gen(REF_PROMPT, ref_image=photo_url)
        print("      SUCCESS:", edited_url2, flush=True)
    except Exception as exc:  # noqa: BLE001
        print("      FAILED:", exc, flush=True)


if __name__ == "__main__":
    main()
