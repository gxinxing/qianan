

## Codely Structured Memories

### User

### Feedback
- [2026-09-06 01:01:26] 用户偏好"分模块蜂群模式"执行改进任务：按模块拆分互不冲突的文件地盘，多个 general-purpose 代理并行修改 + 1 个集成收尾阶段（接线 Makefile、全量校验、git 审阅、提交建议但不自动 commit）。**Why:** 2026-09-06 一次性高效完成 7 模块安全/部署/前端/规则库/测试/依赖修复，用户对并行方式满意。**How to apply:** 多模块批量改进任务默认用此模式；先划文件地盘避免冲突，改动类任务用 general-purpose 而非 explore。
- [2026-09-06 01:55:45] TokenDance API 仅用于千岸跨境电商项目；Codex 与 cc-switch 的设置严禁改动（Codex 保持官方 OAuth 登录）。**Why:** 2026-09-06 为找 TokenDance 凭据只读了 ~/.codex 备份与 cc-switch.db，用户明确纠正"不要搞混"，担心动了 Codex 配置。**How to apply:** 项目需要网关凭据时从 ~/.cc-switch/cc-switch.db providers 表（TokenDance id 6d1039ee-）只读提取，唯一落点 qianan/server/.env；绝不写 ~/.codex/ 或 cc-switch 任何文件。

### Project
- [2026-09-07 17:10:32] 千岸 QianAn 复赛冲刺状态（2026-09-07 部署完成）：✅公网全链路真实模式已上线并实测——前端 https://ai-native-d5gfb0dm2a28d1fe9-1419921079.tcloudbaseapp.com（9 页面 200 含干净 URL），API https://ai-native-d5gfb0dm2a28d1fe9-1419921079.ap-shanghai.app.tcloudbase.com/api/**（QIANAN_MOCK=0 TokenDance 真实模式，health mock:false）；E2E 实测：Amazon 单平台生成 74.9s done、合规一次通过零修订、seedream 主图 2048×2048 多模态实测**无水印**（原水印疑虑未复现）；9 端点 GET 全 200、ideation 真实出 3 条建议；docs/05 已回填实测报告。本地 5 commits 落库（a238817 server 鉴权/6bb5a7b web 重构/249a7e0 deploy 链路/e48c311 消融报告/470ca10 清垃圾 137 文件），工作树干净。**剩余三件事**：①演示视频未录（docs/08 脚本，前置已全就绪）②push 需用户给 remote（git 无 remote）③可选：控制台配预置并发消 7-10s 冷启动。**Why:** 复赛提交四件套中 Demo URL + 技术说明 + 代码仓库三项已就绪，视频是最后缺口。**How to apply:** 下次会话优先录视频；部署迭代一律走 cloudbase/deploy.sh（四条实测坑已内置：linux cp310 wheel 必须非 macOS .so/绝对路径解释器 /var/lang/python310/清 .next 缓存构建/.env.development 与 .env.production 分层）。


- [2026-09-06 10:31:56] 本机测试千岸栈的网络陷阱（2026-09-06 自检发现）：①宿主 8000 被 goofish 项目的 dev server（uvicorn orchestrator.app）占 IPv4，千岸后端容器走宿主 8100，勿动 goofish 进程；②用户开着 Clash 系统代理（127.0.0.1:7890），macOS 例外清单含 localhost 故浏览器直连安全，但 Python urllib 读系统代理时例外不生效——本机脚本测 localhost 接口必须用 curl --noproxy '*' 或 ProxyHandler({})；③本机 shell PATH 不含 /usr/local/bin 与 /opt/homebrew/bin，docker/npx/node 须绝对路径或先 export PATH。**Why:** 三条坑都让自检脚本静默打错目标（502/连不上）。**How to apply:** 任何本机 E2E/冒烟脚本先按这三条排查再怀疑项目代码。

### Reference

