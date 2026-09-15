

## Codely Structured Memories

### User

### Feedback
- [2026-09-06 01:01:26] 用户偏好"分模块蜂群模式"执行改进任务：按模块拆分互不冲突的文件地盘，多个 general-purpose 代理并行修改 + 1 个集成收尾阶段（接线 Makefile、全量校验、git 审阅、提交建议但不自动 commit）。**Why:** 2026-09-06 一次性高效完成 7 模块安全/部署/前端/规则库/测试/依赖修复，用户对并行方式满意。**How to apply:** 多模块批量改进任务默认用此模式；先划文件地盘避免冲突，改动类任务用 general-purpose 而非 explore。
- [2026-09-06 01:55:45] TokenDance API 仅用于千岸跨境电商项目；Codex 与 cc-switch 的设置严禁改动（Codex 保持官方 OAuth 登录）。**Why:** 2026-09-06 为找 TokenDance 凭据只读了 ~/.codex 备份与 cc-switch.db，用户明确纠正"不要搞混"，担心动了 Codex 配置。**How to apply:** 项目需要网关凭据时从 ~/.cc-switch/cc-switch.db providers 表（TokenDance id 6d1039ee-）只读提取，唯一落点 qianan/server/.env；绝不写 ~/.codex/ 或 cc-switch 任何文件。

### Project
- [2026-09-07 17:42:11] 千岸 QianAn 复赛冲刺状态（2026-09-07 部署+推送完成）：✅公网全链路真实模式上线——前端 https://ai-native-d5gfb0dm2a28d1fe9-1419921079.tcloudbaseapp.com，API https://同域前缀.ap-shanghai.app.tcloudbase.com/api/**（TokenDance 真实模式 mock:false）；E2E：Amazon 单平台 74.9s done、合规零修订、主图 2048×2048 无水印；docs/05 已回填实测报告。✅源码已推送 **github.com/gxinxing/qianan（私有）**，main 与 origin 同步（10 commits），工作树干净；推送前已做密钥扫描（users.json/.env 均未入库）。**剩余**：①演示视频未录（docs/08 脚本）——最后缺口；②可选：控制台预置并发消 7-10s 冷启动；③若赛事需评审访问仓库，转公开前注意 CODELY.md 记忆区含本机凭据存放路径提示（cc-switch.db），建议先清理。**Why:** 复赛四件套中 Demo URL/技术说明/代码仓库三项已就绪，视频是唯一缺口。**How to apply:** 下次会话优先录视频；部署迭代走 cloudbase/deploy.sh（四条实测坑内置：linux cp310 wheel/绝对路径解释器 /var/lang/python310/清 .next 缓存构建/.env 分层）；推送直接 git push（origin 已配好）。



- [2026-09-06 10:31:56] 本机测试千岸栈的网络陷阱（2026-09-06 自检发现）：①宿主 8000 被 goofish 项目的 dev server（uvicorn orchestrator.app）占 IPv4，千岸后端容器走宿主 8100，勿动 goofish 进程；②用户开着 Clash 系统代理（127.0.0.1:7890），macOS 例外清单含 localhost 故浏览器直连安全，但 Python urllib 读系统代理时例外不生效——本机脚本测 localhost 接口必须用 curl --noproxy '*' 或 ProxyHandler({})；③本机 shell PATH 不含 /usr/local/bin 与 /opt/homebrew/bin，docker/npx/node 须绝对路径或先 export PATH。**Why:** 三条坑都让自检脚本静默打错目标（502/连不上）。**How to apply:** 任何本机 E2E/冒烟脚本先按这三条排查再怀疑项目代码。

### Reference

