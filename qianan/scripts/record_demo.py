#!/usr/bin/python3
"""千岸 QianAn · 3 分钟真图 Demo 录屏脚本（Playwright）。

前置（由 qianan-dev-bringup skill 拉起）：
  - 后端 :8001 且 QIANAN_MOCK=0（真实百炼网关，主图为真图）
  - 前端 :3000 在线
  - chromium 软链就绪：~/Library/Caches/ms-playwright/chromium-1223 -> chromium-1234

运行：
  /usr/bin/python3 qianan/scripts/record_demo.py
  -> 产出 qianan/scripts/demo_video/webm/xxx.webm（再用 ffmpeg 转 mp4）

注意：本脚本为「可运行骨架」。Bash 工具故障期间无法实测，首次运行时按页面实际
DOM 微调 locator（已在关键步骤加注释）。逐项等待用显式 timeout，避免脆断。
"""
from __future__ import annotations

import os
import sys
import time

from playwright.sync_api import sync_playwright

FRONTEND = os.getenv("DEMO_FRONTEND", "http://localhost:3000")
BACKEND = os.getenv("DEMO_BACKEND", "http://localhost:8001")
# 若已用 API 预生成真实任务，传入其 id 可跳过提交等待；否则留空走完整流程
PRE_TASK_ID = os.getenv("DEMO_TASK_ID", "")
OUT_DIR = os.path.join(os.path.dirname(__file__), "demo_video", "webm")
os.makedirs(OUT_DIR, exist_ok=True)


def _stamp():
    return time.strftime("%Y%m%d-%H%M%S")


def run():
    with sync_playwright() as p:
        # headless=False 以便录到真实渲染；chromium 经软链 1223 解析到 Chrome 151
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=2,
            record_video_dir=OUT_DIR,
        )
        page = ctx.new_page()
        page.set_default_timeout(30000)

        # ---- Shot 1: 首页 ----
        page.goto(FRONTEND + "/", wait_until="networkidle")
        page.wait_for_timeout(2500)  # 口播开场

        # ---- Shot 2: 工作台提交 ----
        page.goto(FRONTEND + "/workbench", wait_until="networkidle")
        page.wait_for_timeout(1500)
        # 填商品名 + 卖点（按页面实际 placeholder 微调 locator）
        page.get_by_placeholder("商品名称").fill("便携 USB-C 榨汁杯 Pro")
        page.get_by_placeholder("核心卖点，每行一条").fill("便携 USB-C 充电\n食品级材质\n6 叶刀片大容量")
        # 勾选 5 平台（默认应已全选，这里确保）
        for plat in ("amazon", "shopee", "aliexpress", "lazada", "tiktokshop"):
            cb = page.locator(f'input[value="{plat}"]')
            if cb.count() and not cb.first.is_checked():
                cb.first.check()
        page.get_by_role("button", name="生成").click()
        page.wait_for_timeout(3000)  # 提交动作定格

        # ---- Shot 3: 结果页真图 ----
        if PRE_TASK_ID:
            page.goto(f"{FRONTEND}/result/{PRE_TASK_ID}", wait_until="networkidle")
        else:
            # 从 Stage 02 运行列表取第一个任务卡链接
            card = page.locator('a[href^="/result/"]').first
            card.wait_for(state="visible", timeout=60000)
            card.click()
        page.wait_for_timeout(8000)  # 等流水线跑完 + 真图生成（wan2.7-image 较慢）
        # 点 Amazon Tab（按平台名定位）
        page.get_by_role("tab", name="Amazon").click() if page.get_by_role("tab", name="Amazon").count() else None
        page.wait_for_timeout(3000)  # 关键帧：真实主图定格

        # ---- Shot 4: F1 编辑即时校验 ----
        title_box = page.get_by_placeholder("标题").first
        title_box.fill("这款便携 USB-C 榨汁杯采用食品级材质大容量设计适合办公室与健身随行使用非常长用来触发长度校验超标")
        title_box.blur()
        page.wait_for_timeout(2500)  # 红色 issue 角标 + 右侧合规报告变红

        # ---- Shot 5: 一键上架 ----
        page.get_by_role("button", name="一键上架").click()
        page.wait_for_timeout(1500)
        # 确认弹窗点 approved
        page.get_by_role("button", name="确认上架").click() if page.get_by_role("button", name="确认上架").count() else None
        page.wait_for_timeout(20000)  # 等 Playwright 驱动模拟后台 + 截图留痕 + live

        # ---- Shot 6: 文件库 + 后台 ----
        page.goto(FRONTEND + "/files", wait_until="networkidle")
        page.wait_for_timeout(3000)
        page.goto(FRONTEND + "/admin", wait_until="networkidle")
        page.wait_for_timeout(3000)

        ctx.close()
        browser.close()
        print(f"DONE. video in {OUT_DIR}")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:  # noqa: BLE001
        print("RECORD FAILED:", repr(exc), file=sys.stderr)
        sys.exit(1)
