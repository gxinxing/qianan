"""test_swarm_evo_blackboard.py — 黑板持久化测试。

验收：
  - save() 后 load()，状态完全恢复
  - 中途中断，resume() 能找回 action_history
  - 保存的 JSON 是人类可读的 dict
"""
from __future__ import annotations

import json

import pytest

from app.agents.swarm.blackboard import Blackboard

# ---------------------------------------------------------------- 工具


def _bb(platforms=("amazon", "shopee")):
    bb = Blackboard(list(platforms))
    return bb


# ---------------------------------------------------------------- 1. save / load 完整往返


def test_blackboard_save_and_load(tmp_path):
    """save() 后 load()，核心状态字段完全一致。"""
    bb = _bb()
    bb.mark_understanding({"product_type": "榨汁杯"})
    bb.mark_copy("amazon", display_name="Amazon")
    bb.mark_reviewed("amazon", [])
    bb.log_action("test_action", "pytest", True, "测试")

    save_path = tmp_path / "test_bb.json"
    bb.save(save_path)

    bb2 = Blackboard.load(save_path)

    assert bb2.goal == bb.goal
    assert bb2.status == bb.status
    assert bb2.project_id == bb.project_id
    assert bb2.action_history == bb.action_history
    # 平台状态
    assert bb2.platforms["amazon"].copy_version == bb.platforms["amazon"].copy_version
    assert bb2.platforms["amazon"].review_version == bb.platforms["amazon"].review_version
    assert bb2.platforms["shopee"].copy_version == 0


# ---------------------------------------------------------------- 2. 中途恢复 action_history


def test_blackboard_resume_after_partial_run(tmp_path):
    """save 两步操作后 load，action_history 不丢。"""
    bb = _bb(["amazon"])
    bb.log_action("understand_product", "worker", True, "ok")
    bb.log_action("generate_copy", "worker", True, "ok")
    bb.status = "running"  # 模拟中途

    p = tmp_path / "partial.json"
    bb.save(p)

    bb2 = Blackboard.load(p)
    assert len(bb2.action_history) == 2
    assert bb2.action_history[0]["action"] == "understand_product"
    assert bb2.action_history[1]["action"] == "generate_copy"
    assert bb2.status == "running"


# ---------------------------------------------------------------- 3. JSON 可读性


def test_blackboard_json_is_readable(tmp_path):
    """保存的文件是合法 JSON，包含必要的顶层键。"""
    bb = _bb(["amazon"])
    p = tmp_path / "readable.json"
    bb.save(p)

    raw = p.read_text(encoding="utf-8")
    data = json.loads(raw)

    required_keys = {"project_id", "run_id", "goal", "status", "platforms", "action_history"}
    assert required_keys.issubset(data.keys())
    assert isinstance(data["platforms"], dict)
    assert isinstance(data["action_history"], list)


# ---------------------------------------------------------------- 4. resume 不存在时返回 None


def test_blackboard_resume_missing_returns_none(tmp_path):
    """resume 找不到文件时不抛异常，返回 None。"""
    result = Blackboard.resume("nonexistent_task_id_12345", data_dir=tmp_path)
    assert result is None


# ---------------------------------------------------------------- 5. 原子写（tmp → replace 不留半写文件）


def test_blackboard_save_atomic(tmp_path):
    """save 完成后不应有 .tmp 文件残留。"""
    bb = _bb()
    p = tmp_path / "atomic.json"
    bb.save(p)
    tmp_file = p.with_suffix(".tmp")
    assert not tmp_file.exists(), ".tmp 文件不应残留"
    assert p.exists()


# ---------------------------------------------------------------- 5. elapsed 从保存点续算


def test_blackboard_load_keeps_elapsed(tmp_path):
    """save 时 elapsed>0，load 后 elapsed 从保存点续算（≥ 保存值，不归零）。"""
    import time

    bb = _bb()
    time.sleep(0.01)  # 保证 elapsed > 0
    bb.mark_understanding({"product_type": "榨汁杯"})
    saved = bb.elapsed
    assert saved > 0

    save_path = tmp_path / "elapsed.json"
    bb.save(save_path)
    bb2 = Blackboard.load(save_path)

    assert bb2.elapsed >= saved, "恢复后计时不应归零"


# ---------------------------------------------------------------- 6. Supervisor 落盘接线


def test_supervisor_checkpoint_persists(tmp_path):
    """Supervisor._checkpoint() 按 _save_path 落盘；黑板核心状态可从盘上恢复。"""
    from app.agents.swarm.supervisor import Supervisor

    class _Client:
        is_mock = True

        def chat(self, system, user):
            return "mock"

        def chat_with_tools(self, messages, schemas):
            return {"content": "mock", "tool_calls": []}

    sup = Supervisor(_Client(), Blackboard(["amazon"]))
    sup._save_path = tmp_path / "swarm" / "task-1.json"

    sup.bb.mark_understanding({"product_type": "榨汁杯"})
    sup._checkpoint()

    assert sup._save_path.exists(), "动作后黑板应已落盘"
    restored = Blackboard.load(sup._save_path)
    assert restored.understanding_version == sup.bb.understanding_version


def test_supervisor_checkpoint_never_blocks(tmp_path):
    """落盘失败只告警不抛异常——持久化是旁路能力，绝不阻断主流程。"""
    from app.agents.swarm.supervisor import Supervisor

    class _Client:
        is_mock = True

        def chat(self, system, user):
            return "mock"

        def chat_with_tools(self, messages, schemas):
            return {"content": "mock", "tool_calls": []}

    sup = Supervisor(_Client(), Blackboard(["amazon"]))
    blocker = tmp_path / "blocker.txt"
    blocker.write_text("我是文件，不是目录")
    sup._save_path = blocker / "swarm" / "x.json"  # parent 是文件 → mkdir 必败

    sup._checkpoint()  # 不应抛异常

    assert sup.bb.status == "running"  # 黑板状态不受影响


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
