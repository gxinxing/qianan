#!/usr/bin/env python3
"""万相 wan2.7-image 可用性自检。

用法：
    cd qianan/server && .venv/bin/python check_wan27.py

为什么需要这个脚本：
    百炼在**账户欠费**时，即使有免费额度 / 资源包 / 节省计划都无法调用，
    一律返回 `400 Arrearage`。这类问题在应用日志里表现为"生图失败并回退"，
    很容易被误判成模型名或代码错误。用这个脚本可以直接看出卡在哪一层。

退出码：0 = 可用；1 = 不可用（原因会打印出来）。
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

NATIVE = "https://dashscope.aliyuncs.com/api/v1"
#: 万相 2.x 用这个端点（text2image/image-synthesis 会报 "url error"），且**同步返回**
SUBMIT = f"{NATIVE}/services/aigc/multimodal-generation/generation"


def _load_key() -> str:
    for line in open(".env", encoding="utf-8"):
        line = line.strip()
        if line.startswith("QIANAN_DASHSCOPE_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def main() -> int:
    key = _load_key()
    if not key:
        print("✗ .env 里没有 QIANAN_DASHSCOPE_API_KEY")
        return 1
    print(f"API Key: {key[:10]}...（长度 {len(key)}）")

    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    # ① 先看 key 本身是否有效、能看见哪些模型
    try:
        req = urllib.request.Request(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/models", headers=headers
        )
        ids = [m.get("id", "") for m in json.loads(op.open(req, timeout=30).read()).get("data", [])]
        print(f"✓ Key 有效，可见 {len(ids)} 个模型")
        wan = [i for i in ids if "wan" in i.lower() and "image" in i.lower()]
        print(f"  万相图像模型: {wan or '（该 Key 未授权任何万相图像模型）'}")
    except urllib.error.HTTPError as exc:
        print(f"✗ Key 无效或被停用: HTTP {exc.code}")
        return 1

    # ② 真正出一张图（注意：这会消耗 1 张额度）
    print("\n调用 wan2.7-image 出图（1024*1024，会消耗 1 张额度）...")
    payload = {
        "model": "wan2.7-image",
        "input": {
            "messages": [
                {"role": "user", "content": [{"text": "a red apple on a white background"}]}
            ]
        },
        "parameters": {"size": "1024*1024", "n": 1},
    }
    try:
        req = urllib.request.Request(SUBMIT, data=json.dumps(payload).encode(), headers=headers)
        data = json.loads(op.open(req, timeout=180).read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")
        if "Arrearage" in body:
            print("✗ 账户欠费（Arrearage）")
            print("  → 欠费状态下，免费额度 / 资源包 / 节省计划一律不生效，必须先结清。")
            print("  → 去 费用与成本 控制台看「账户可用额度」，<0 即为欠费。")
        else:
            print(f"✗ 调用失败 HTTP {exc.code}: {body[:200]}")
        return 1

    # 同步返回：结果直接在 output.choices[0].message.content 里
    for part in (
        (((data.get("output") or {}).get("choices") or [{}])[0].get("message") or {}).get("content")
        or []
    ):
        if isinstance(part, dict) and part.get("image"):
            used = (data.get("usage") or {}).get("image_count")
            print(f"✓ 出图成功（本次 {used} 张）\n  {part['image'][:100]}")
            print("  注意：该 URL 带 Expires，是临时签名地址，应用内会自动转存")
            _show_quota()
            return 0

    print(f"✗ 返回中无图片: {json.dumps(data, ensure_ascii=False)[:220]}")
    return 1


def _show_quota() -> None:
    """打印应用记录的额度消耗。"""
    try:
        q = json.loads(open("data/wan_image_quota.json", encoding="utf-8").read())
        print(f"  应用已用额度: {q.get('used')}/{q.get('quota')} 张")
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    sys.exit(main())
