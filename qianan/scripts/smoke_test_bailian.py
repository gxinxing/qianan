"""百炼 Token Plan API 冒烟测试（Week 1 D1 验收）。

跑通三项即 D1 完成：
  1. 文本生成（qwen3.7-max，/chat/completions）
  2. 图片生成（qwen-image-2.0，走 chat 路由 + 列表 content）
  3. 视觉理解（可选 —— 当前网关无 VL 模型，配置 QIANAN_VL_MODEL 后才测）

用法：
  cd qianan/server && pip install -r requirements.txt   # 首次
  python ../scripts/smoke_test_bailian.py

密钥从 server/.env 自动加载（BAILIAN_API_KEY）。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 让脚本能 import server/app 里的客户端（顺带完成 .env 加载）
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from app.bailian import client as C  # noqa: E402


def test_text() -> bool:
    try:
        text = C.BailianClient().chat(
            "你是跨境电商 Listing 文案专家。", "用英文为一款便携榨汁杯写一条 30 词以内的卖点。"
        )
        print(f"  返回：{text.strip()[:100]}...")
        return bool(text.strip())
    except Exception as exc:  # noqa: BLE001
        print(f"  失败：{exc}")
        return False


def test_image() -> bool:
    try:
        url = C.BailianClient().image_gen("电商主图：纯白背景上一台便携榨汁杯，商业摄影，主体居中，无水印无文字")
        print(f"  生成图片：{url[:110]}...")
        return url.startswith("http")
    except Exception as exc:  # noqa: BLE001
        print(f"  失败：{exc}")
        return False


def test_vision() -> bool | None:
    if not C.VL_MODEL:
        print("  跳过：当前网关未配置视觉理解模型（QIANAN_VL_MODEL 为空）")
        return None
    try:
        text = C.BailianClient().vision(
            "https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg",
            "这张图里的商品是什么？一句话回答。",
        )
        print(f"  返回：{text[:100]}")
        return bool(text.strip())
    except Exception as exc:  # noqa: BLE001
        print(f"  失败：{exc}")
        return False


def main() -> int:
    import os

    if not os.environ.get("BAILIAN_API_KEY"):
        print("✗ 未找到 BAILIAN_API_KEY，请先在 server/.env 中填入黑客松专属 key")
        return 2

    print(f"基地址：{C.BASE_URL}")
    print(f"文本模型：{C.TEXT_MODEL} | 图片模型：{C.IMAGE_MODEL} | VL：{C.VL_MODEL or '（未配置）'}\n")

    results = []

    print(f"[1/3] 文本生成 {C.TEXT_MODEL} ...")
    results.append(("文本生成", test_text(), True))

    print(f"[2/3] 图片生成 {C.IMAGE_MODEL} ...")
    results.append(("图片生成", test_image(), True))

    print(f"[3/3] 视觉理解 ...")
    results.append(("视觉理解", test_vision(), False))

    print("\n========== 冒烟测试结果 ==========")
    ok = True
    for name, passed, required in results:
        if passed is None:
            print(f"  SKIP  {name}（网关暂不支持，非阻塞）")
            continue
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
        if required:
            ok = ok and passed
    print("==================================")
    print("D1 验收通过：文本 + 图片生成均已跑通。" if ok else "存在必选项失败，请检查上方报错。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
