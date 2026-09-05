"""pytest 公共配置：sys.path 注入 + 规则库定位 + overlay 屏蔽（全仓库唯一公共夹具层）。

约定：
- 测试只做纯逻辑校验：不调外部 API、不触网、不初始化真实模型客户端；
- 规则 JSON 统一从 qianan/server/rules 加载（相对路径定位，禁止硬编码绝对路径）；
- 已安装技能/进化补丁的规则 overlay 被屏蔽，保证断言确定性。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

SERVER_ROOT = Path(__file__).resolve().parent.parent
RULES_DIR = SERVER_ROOT / "rules"

# sys.path 注入必须先于任何 `import app.*`（pytest 先导入 conftest 再收集测试模块）
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

# rules_store 在 import 时解析 RULES_DIR：必须先落 env 再触发任何 app 包导入
os.environ["QIANAN_RULES_DIR"] = str(RULES_DIR)


@pytest.fixture(autouse=True)
def deterministic_rules(monkeypatch: pytest.MonkeyPatch):
    """屏蔽规则 overlay 并清空 lru_cache，让 load_rules() 只反映 rules/*.json。

    本地 data/skills/installed/ 若装了 eu-gpsr 等技能，会给 amazon/aliexpress
    追加禁词组与检查项，破坏对 check_id 集合的确定性断言，故在测试内一律屏蔽。
    """
    from app import rules_store, skill_store

    monkeypatch.setattr(skill_store, "rules_patch", lambda platform: {})
    rules_store.cache_clear()
    yield
    rules_store.cache_clear()
