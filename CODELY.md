

## Codely Structured Memories

### User

### Feedback
- [2026-09-06 01:01:26] 用户偏好"分模块蜂群模式"执行改进任务：按模块拆分互不冲突的文件地盘，多个 general-purpose 代理并行修改 + 1 个集成收尾阶段（接线 Makefile、全量校验、git 审阅、提交建议但不自动 commit）。**Why:** 2026-09-06 一次性高效完成 7 模块安全/部署/前端/规则库/测试/依赖修复，用户对并行方式满意。**How to apply:** 多模块批量改进任务默认用此模式；先划文件地盘避免冲突，改动类任务用 general-purpose 而非 explore。
- [2026-09-06 01:55:45] TokenDance API 仅用于千岸跨境电商项目；Codex 与 cc-switch 的设置严禁改动（Codex 保持官方 OAuth 登录）。**Why:** 2026-09-06 为找 TokenDance 凭据只读了 ~/.codex 备份与 cc-switch.db，用户明确纠正"不要搞混"，担心动了 Codex 配置。**How to apply:** 项目需要网关凭据时从 ~/.cc-switch/cc-switch.db providers 表（TokenDance id 6d1039ee-）只读提取，唯一落点 qianan/server/.env；绝不写 ~/.codex/ 或 cc-switch 任何文件。

### Project
- [2026-09-06 01:56:22] 千岸 QianAn 复赛冲刺状态（2026-09-06）：7 模块蜂群修复已完成（安全鉴权/Docker链路/前端/规则库统一/测试CI/依赖锁定/仓库卫生），全量校验绿；提交物仍未落地：①部署拿 Demo URL（Docker mirror 已清理：移除失效 1panel.live、留 daocloud；docker-up 冒烟验证中）②按 docs/04 脚本录演示视频 ③推送源码仓库 ④API 已切换 TokenDance 网关（tokendance.space/gateway/v1：qwen3.7-max 文本 / seedream-5.0-lite 图像直连式须 IMAGE_SIZE=2048x2048 / qwen3-vl-plus VL 已恢复；本机 Py3.9 LibreSSL 对该网关不兼容，须 .venv 3.10 或 Docker）。**Why:** 复赛提交物表格三项全 🚧 是最大失分风险。**How to apply:** 下次会话优先推进部署/录屏/推送三件事；遗留技术债见集成报告（main.py 拆分、部署包 app 代码旧快照、task_store 持久化）。



### Reference

