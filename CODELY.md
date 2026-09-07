

## Codely Structured Memories

### User

### Feedback
- [2026-09-06 01:01:26] 用户偏好"分模块蜂群模式"执行改进任务：按模块拆分互不冲突的文件地盘，多个 general-purpose 代理并行修改 + 1 个集成收尾阶段（接线 Makefile、全量校验、git 审阅、提交建议但不自动 commit）。**Why:** 2026-09-06 一次性高效完成 7 模块安全/部署/前端/规则库/测试/依赖修复，用户对并行方式满意。**How to apply:** 多模块批量改进任务默认用此模式；先划文件地盘避免冲突，改动类任务用 general-purpose 而非 explore。
- [2026-09-06 01:55:45] TokenDance API 仅用于千岸跨境电商项目；Codex 与 cc-switch 的设置严禁改动（Codex 保持官方 OAuth 登录）。**Why:** 2026-09-06 为找 TokenDance 凭据只读了 ~/.codex 备份与 cc-switch.db，用户明确纠正"不要搞混"，担心动了 Codex 配置。**How to apply:** 项目需要网关凭据时从 ~/.cc-switch/cc-switch.db providers 表（TokenDance id 6d1039ee-）只读提取，唯一落点 qianan/server/.env；绝不写 ~/.codex/ 或 cc-switch 任何文件。

### Project
- [2026-09-07 14:31:38] 千岸 QianAn 复赛冲刺状态（2026-09-07 扫描，距截止 9.13 约 6 天）：消融实验已完成（docs/10+ablation_study.py，TokenDance 真实跑）；CloudBase 已部署云函数 API（ai-native-d5gfb0dm2a28d1fe9-1419921079.ap-shanghai.app.tcloudbase.com，/api/* 200）但四坑：①QIANAN_MOCK=1 返回罐头模板数据 ②前端静态托管未部署成功（/ 与所有页面 404，评审打开只有 API）③deploy_pkg 与 cloudfunctions/qianan-api 双部署包均与源码漂移 10+ 文件 ④cloudbaserc 缺 QIANAN_IMAGE_SIZE、VL 置空、BASE_URL 仍指阿里 token-plan 而非 TokenDance——切真实模式必挂。另：49 文件未提交（auth 多租户/result 路由重构/paths/owners/消融全部 9.6-9.7 新工作）、git 无 remote 从未 push、演示视频未录、docs/05 集成验证报告仍是空模板、seedream「AI生成」水印未实测。**Why:** 四件提交物（可运行 Demo/代码仓库/演示视频/技术说明）无一就绪，且部署有"假可用"迷惑性——API 通但前端 404 且是 mock。**How to apply:** 下一会话优先级：同步 deploy_pkg→修 cloudbaserc 环境变量（加 IMAGE_SIZE=2048x2048、VL 模型、换 TokenDance BASE_URL）→部署前端托管→公网全链路 E2E→commit+push→按 docs/08 录视频。

- [2026-09-06 10:31:56] 本机测试千岸栈的网络陷阱（2026-09-06 自检发现）：①宿主 8000 被 goofish 项目的 dev server（uvicorn orchestrator.app）占 IPv4，千岸后端容器走宿主 8100，勿动 goofish 进程；②用户开着 Clash 系统代理（127.0.0.1:7890），macOS 例外清单含 localhost 故浏览器直连安全，但 Python urllib 读系统代理时例外不生效——本机脚本测 localhost 接口必须用 curl --noproxy '*' 或 ProxyHandler({})；③本机 shell PATH 不含 /usr/local/bin 与 /opt/homebrew/bin，docker/npx/node 须绝对路径或先 export PATH。**Why:** 三条坑都让自检脚本静默打错目标（502/连不上）。**How to apply:** 任何本机 E2E/冒烟脚本先按这三条排查再怀疑项目代码。

### Reference

