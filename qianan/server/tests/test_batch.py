"""批量接口 NameError 回归测试（对应审计发现 #4：main.py:355 引用未导入的 ALL_PLATFORMS）。

修复前：generate_batch 在 `req.platforms` 非空时执行
    item.platforms = [p for p in req.platforms if p in ALL_PLATFORMS] ...
其中 ALL_PLATFORMS 仅在 generate() 内局部导入，generate_batch 作用域未定义 → NameError（500）。
修复后：ALL_PLATFORMS 提到底层 schemas 导入，批量请求应正常返回 200 + task_ids。

后台 run_pipeline 被替换成 noop，本测试只验证「请求处理器不再因未定义名称崩溃」。
"""
from __future__ import annotations


async def _async_noop(*args, **kwargs):  # noqa: ANN001
    return None


def test_generate_batch_no_name_error(monkeypatch):
    monkeypatch.setenv("QIANAN_MOCK", "1")
    # 后台任务不实际执行，避免无关副作用
    import app.main as main_app

    monkeypatch.setattr(main_app, "run_pipeline", _async_noop)

    from fastapi.testclient import TestClient

    client = TestClient(main_app.app)
    payload = {
        "items": [
            {
                "product_name": "Portable Blender 380ml",
                "selling_points": "USB-C fast charge; easy to clean",
                "category": "home_kitchen",
                "platforms": ["amazon"],
            }
        ],
        # 含一个非法平台 bogus，验证过滤器按已知平台裁剪而非崩溃
        "platforms": ["amazon", "shopee", "bogus"],
    }
    resp = client.post("/api/generate/batch", json=payload)
    assert resp.status_code == 200, f"批量接口应返回 200，实际 {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "task_ids" in body and body["task_ids"], "应返回 task_ids"
