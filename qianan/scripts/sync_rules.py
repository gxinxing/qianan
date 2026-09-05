"""规则库统一同步：qianan/rules（单一数据源）→ 其余运行时拷贝。

规则库是「多平台合规引擎」的核心资产，仓库里存在 4 份拷贝，分别服务于不同
运行时（加载逻辑见 server/app/rules_store.py::_resolve_rules_dir）：

  数据源  qianan/rules                                       本地 uvicorn（parents[2]/rules 优先命中）
  ├─ 目标  qianan/server/rules                                 Docker 镜像（/app/rules，parents[1] 兜底命中）
  ├─ 目标  qianan/server/cloudfunctions/qianan-api/rules       云函数部署包（app 与 rules 同级发布）
  └─ 目标  qianan/server/deploy_pkg/rules                     SCF zip 部署包（app 与 rules 同级发布）

只编辑数据源 qianan/rules/*.json，然后跑本脚本扩散到全部目标，禁止直接改目标目录
（部署产物会被本脚本整体覆盖）。

用法：
  python qianan/scripts/sync_rules.py            # 同步：数据源 → 全部目标目录
  python qianan/scripts/sync_rules.py --check   # 只比对不写入；任一拷贝漂移时 exit 1（可接 CI/Makefile）
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

QIANAN_DIR = Path(__file__).resolve().parents[1]
SOURCE_DIR = QIANAN_DIR / "rules"
TARGET_DIRS = [
    QIANAN_DIR / "server" / "rules",
    QIANAN_DIR / "server" / "cloudfunctions" / "qianan-api" / "rules",
    QIANAN_DIR / "server" / "deploy_pkg" / "rules",
]


def _source_files() -> list[Path]:
    files = sorted(SOURCE_DIR.glob("*.json"))
    if not files:
        print(f"✗ 数据源目录没有 JSON：{SOURCE_DIR}")
        sys.exit(2)
    return files


def _diff_target(files: list[Path], target: Path) -> list[str]:
    """返回目标目录相对数据源的漂移清单（缺文件 / 内容不一致 / 多余文件）。"""
    issues: list[str] = []
    for src in files:
        dst = target / src.name
        if not dst.exists():
            issues.append(f"缺失  {src.name}")
        elif dst.read_bytes() != src.read_bytes():
            issues.append(f"漂移  {src.name}")
    extra = sorted(p.name for p in target.glob("*.json") if p.name not in {f.name for f in files})
    for name in extra:
        issues.append(f"多余  {name}（数据源中不存在）")
    return issues


def cmd_check(files: list[Path]) -> int:
    print(f"数据源：{SOURCE_DIR.relative_to(QIANAN_DIR.parent)}（{len(files)} 个平台 JSON）")
    drift = False
    for target in TARGET_DIRS:
        rel = target.relative_to(QIANAN_DIR.parent)
        if not target.is_dir():
            print(f"✗ {rel}：目录不存在")
            drift = True
            continue
        issues = _diff_target(files, target)
        if issues:
            drift = True
            print(f"✗ {rel}：")
            for line in issues:
                print(f"    {line}")
        else:
            print(f"✓ {rel}：与数据源一致（{len(files)} 个文件）")
    print("CHECK PASS：全部拷贝与数据源一致。" if not drift else "CHECK FAIL：存在漂移，运行 sync_rules.py 同步。")
    return 1 if drift else 0


def cmd_sync(files: list[Path]) -> int:
    # 先验证数据源 JSON 合法，避免把坏文件扩散到部署产物
    for src in files:
        try:
            json.loads(src.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"✗ 数据源 JSON 非法，中止同步：{src.name}: {exc}")
            return 2

    print(f"数据源：{SOURCE_DIR.relative_to(QIANAN_DIR.parent)}（{len(files)} 个平台 JSON）")
    for target in TARGET_DIRS:
        rel = target.relative_to(QIANAN_DIR.parent)
        target.mkdir(parents=True, exist_ok=True)
        copied = skipped = 0
        for src in files:
            dst = target / src.name
            if dst.exists() and dst.read_bytes() == src.read_bytes():
                skipped += 1
                continue
            shutil.copyfile(src, dst)
            if dst.read_bytes() != src.read_bytes():
                print(f"✗ 写入后校验失败：{dst}")
                return 2
            print(f"  同步 {src.name} → {rel}/")
            copied += 1
        print(f"✓ {rel}：{copied} 个更新 / {skipped} 个已一致")
    print("SYNC DONE：全部目标目录已与数据源对齐。")
    return cmd_check(files)  # 同步完自检，复用比对逻辑与退出码语义


def main() -> int:
    parser = argparse.ArgumentParser(
        description="规则库统一同步：qianan/rules → server/rules、cloudfunctions、deploy_pkg 三份运行时拷贝"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只比对数据源与各目标目录是否一致，不写入任何文件；一致 exit 0，漂移 exit 1",
    )
    args = parser.parse_args()

    files = _source_files()
    return cmd_check(files) if args.check else cmd_sync(files)


if __name__ == "__main__":
    sys.exit(main())
