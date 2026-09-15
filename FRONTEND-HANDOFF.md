# 前端视觉与动效交接

更新日期：2026-09-15  
项目：千岸 QianAn  
前端目录：`qianan/web/`  
交接时 HEAD：`0587d8e`，写入本交接前工作区干净。该提交包含其他交付工作，不应当作纯前端改版提交。

## 1. 用户已确认的方向

1. 原首页像表单，希望参考 OpenAI Agent 的前端体验。
2. 改版后不能再混用深蓝色，注册页也不要深蓝色。
3. 参考用户提供的《动画提升Apple 级 Spring 动效.md》，结合当前页面加入克制的 Spring 动效。

**继续沿用：白底、暖灰侧栏、炭黑主按钮、少量灰绿色选中状态；以任务输入为中心。**

避免重新加入深蓝大幅 Hero、多个并列输入框、复杂宣传卡片、过度弹跳。当前首页采用 Agent 风格的任务入口，提交后仍跳转结果页，并没有改成首页内流式聊天。

动效参考原文：
`/Users/simon/Documents/04_Knowledge & Efficiency/Obsidian Vault/3-Resources/编程提示词/动画提升Apple 级 Spring 动效.md`

## 2. 本轮完成的范围

### 首页 `/`

- 左侧工作区导航，右侧居中标题与主要输入框。
- 原商品名、卖点、任务诉求的大表单，改为一个商品与需求描述区。
- 图片附件入口在输入框下方，保留上传、拖入、预览、移除与原有压缩逻辑。
- 平台选择、可选商品名、额外任务要求收进可展开设置。
- 保留商品样例与任务快捷入口；东南亚入口会选择 Shopee、Lazada、TikTok Shop。
- 原选品、产出物与能力说明收进“了解千岸能为你做什么”。
- 原顶部模拟运行轨迹已移除，避免与真实执行状态混淆。
- 手机侧栏可开关，关闭后不可键盘访问，支持 Esc 关闭。
- Enter 提交、Shift+Enter 换行；中文输入法组合输入期间不会误提交。

### 共享配色

- `brand` 色阶从深蓝改成灰绿到炭黑。
- `ink` 色阶从蓝灰改成暖中性色。
- 全局 CSS 变量、选区、焦点、纹理线色一起更新。
- 使用共享 token 的导航、工作台等页面会继承新配色。
- 红色错误、绿色成功等语义状态色保留。

### 登录 `/login`、注册 `/register`

- 暖灰背景、白色卡片、炭黑按钮、灰绿色焦点。
- 增加返回首页入口；注册说明改成用户能理解的“跨境上新工作区”。
- 增加卡片进场、按钮按压和错误/成功反馈。
- 认证接口、密码规则、登录注册后的路由行为没有重新设计。

### 动效

- 安装 `framer-motion`，包版本范围为 `^13.3.0`，已更新锁文件。
- 全局 `MotionConfig reducedMotion="user"`。
- 首页标题与输入框分两组轻入场；输入框延迟 0.08 秒。
- 按钮按下缩放到 0.97，再通过 Spring 回弹。
- 平台设置以高度与透明度展开；退出时立即设为 `inert`。
- 手机侧栏使用 CSS 自定义属性驱动 Spring 位移。
- 路由通过 Next.js `template.tsx` 做轻淡入，不保留旧页面，也没有做路由退出动画。
- 减少动态效果模式显式关闭位移、缩放、展开高度动画与进场延迟。

## 3. 文件地图

| 文件（相对 `qianan/web/`） | 职责 |
| --- | --- |
| `app/page.tsx` | 首页布局、平台设置、附件、样例、任务提交 |
| `app/globals.css` | 全局变量与 `.agent-home-*` 布局样式，手机断点 700px |
| `tailwind.config.js` | 共享 brand/ink 色阶 |
| `app/login/page.tsx` | 登录卡片与反馈 |
| `app/register/page.tsx` | 注册卡片与反馈 |
| `app/layout.tsx` | 全局 MotionProvider、原 AuthProvider |
| `app/template.tsx` | 新路由内容淡入，不使用整体 transform |
| `components/MotionUI.tsx` | MotionProvider、Enter、PressButton、Reveal、Feedback、SidebarMotion |
| `lib/motion.ts` | Spring 参数和短退出曲线 |
| `package.json`、`package-lock.json` | Framer Motion 依赖 |
| `CLAUDE.md`、`lib/CLAUDE.md` | 动效模块说明 |

不要把所有页面的 transform 加到共同祖先：可能影响 fixed 导航的定位。不要用共享 `.card` 的全局缩放来替代具体组件交互。

## 4. 配色和运动参数

主要颜色：

| 用途 | 值 |
| --- | --- |
| 主内容背景 | `#ffffff` |
| 侧栏、页面暖灰底 | `#f7f7f5` |
| 主文字 | `#252525` |
| 主按钮 / brand-800 | `#272824` |
| 常用边框 / ink-200 | `#deded9` |
| 浅选中背景 / brand-50 | `#f4f5f0` |
| 焦点、灰绿强调 | `#939b86` / `#777f6a` |

共享 Spring：

- `snappy`：stiffness 400 / damping 30，用于按压、反馈。
- `gentle`：stiffness 300 / damping 35，用于进场、设置面板、侧栏。
- `smooth`：stiffness 200 / damping 40 / mass 1.2，已定义，暂未作为独立场景使用。
- 短退出：0.14 秒，曲线 `[0.22, 1, 0.36, 1]`。

首页当前已有“路由淡入 + 标题 + 输入框”三个进场单元，不再叠加整列图标或样例逐个弹入。

## 5. 必须保留的业务兼容细节

首页仍调用 `createTask`，成功后跳转 `/result?taskId=...`。

- `selling_points`：主要描述文本，最多 2000 字符。
- `product_name`：优先补充商品名，否则取描述前 200 字符。
- `request_text`：优先额外任务要求，否则取描述前 300 字符。
- `category`、图片、平台仍按原接口传递。

**不要直接删除商品名 fallback。** 审查发现后端 SKU 生成依赖 `product_name`；若所有自由描述任务都传空名称，可能产生重复商品标识。当前 fallback 是兼容做法，不等于已经实现语义商品名抽取。

描述编辑时会清掉此前样例遗留的商品名称，防止用户换商品后沿用旧名称。纯图片任务继续遵循原流程；本轮未验证其完整生成链路。

## 6. 已做的验证与边界

### 已通过 / 已观察确认

- 最终 TypeScript 检查：`npm run typecheck -- --incremental false`。
- 改动的独立代码审查未发现重要回归。
- 首页桌面 1440×1000、手机 390×844 静态效果检查。
- 样例商品填入、平台 5→4 切换、手机菜单开关。
- 配色阶段注册/登录按钮实测为 `rgb(39, 40, 36)`。
- 配色阶段手机布局无横向溢出。
- Spring 阶段平台设置正常展开。
- 减少动态效果模式：平台收起并卸载、手机侧栏 Esc 关闭后 `inert=true`。
- 空输入提交后的校验文案已在 DOM 中出现。

### 不应当宣称全部端到端通过

- 本地首次编译曾超过一分钟，浏览器测试发生过超时；之后独立检查确认面板可以展开。
- 最后一条自动化脚本在 `getByRole('alert')` 处失败：同时匹配业务错误和 Next.js 路由 announcer。这是测试选择器冲突；仍需要用 `main [role="alert"]` 或具体文案重新跑完整脚本。
- 最后脚本在上述位置结束，没有执行完该脚本的后续移动端检查。
- 没有实际注册新账户、验证认证服务、运行付费生成、发布商品或完整后端任务链路。
- 注册成功动效已接入，但未用真实注册成功现场验收。
- 没有真机手感、低端设备性能、生产包体积或全路由视觉回归结果。

## 7. 预览与部署

会话中使用的本地预览：`http://127.0.0.1:3100/`。

这是本地调试入口，接手时先确认进程是否还在。标准开发脚本默认端口是 3000，可在 `qianan/web/` 使用：

```sh
npm ci
npm run dev
```

需要 3100 且避免与其他 Next.js 实例争用构建目录时，可参考会话使用的独立服务方式：

```sh
WATCHPACK_POLLING=true node - <<'JS'
const next = require('next');
const http = require('http');
const app = next({ dev: true, dir: process.cwd(), conf: { distDir: '.next-agent-preview' } });
app.prepare().then(() => {
  http.createServer(app.getRequestHandler()).listen(3100, '127.0.0.1');
});
JS
```

启动前确认实际生效的构建目录，避免多个进程同时写同一个 `.next`。项目配置是静态导出 `output: "export"`；本轮没有执行公网部署或验证公网版本。不要把本地看到的新版当作已上线。

## 8. 后续建议顺序

1. 先与用户确认静态风格和实际动效手感，不再大幅重做首页。
2. 修正测试里的 alert 选择器，补完正常/减少动态效果、注册校验、手机切换与桌面 resize 回归。
3. 若要继续全站统一，重点查看 `/studio` 和 `components/chat/*`：该处仍有原暗色、青色、紫色样式，本轮没有整体重做。
4. 结果、批量、Agent 中枢、文件等页面只继承了共享色阶与路由淡入，没有逐页做组件动效验收。
5. 根据用户反馈决定是否增加侧栏焦点管理、加载状态切换、列表与卡片微动效；保持克制。
6. 发布前执行生产构建和静态导出检查，再按用户授权部署。

## 9. 给下一位执行者的简短提示

> 先读 FRONTEND-HANDOFF.md 和 qianan/web/CLAUDE.md。用户已确认 OpenAI Agent 风格、暖灰黑白配色、去深蓝，以及克制的 Spring 动效。保留首页现有任务 API 与商品名 fallback。不要混入旧版 Studio 的深色视觉，不要宣称公网已更新或完整业务链路已通过。先补浏览器验证，再根据用户反馈做局部改动。

## 10. 补充：残留深蓝清理（2026-09-15）

按"去深蓝"全局口径，把主流程页面里仍用 raw `blue-*` 的位置替换为共享 `brand` 灰绿色 token（只换色，不重做整页）：

- `app/(app)/batch/page.tsx`：`running` 徽标 `bg-blue-50 text-blue-600` → `bg-brand-50 text-brand-700`；进度条 `bg-blue-400` → `bg-brand-500`。
- `app/rules/page.tsx`：`standard` 徽标 `bg-blue-50 text-blue-700` → `bg-brand-50 text-brand-700`。
- `components/chat/Sidebar.tsx`：Logo / 新对话按钮渐变 `from-cyan-500 to-blue-600` 等 → `from-brand-400 to-brand-500` / `from-brand-500 to-brand-700`，阴影 `shadow-cyan-*/20` → `shadow-brand-*/20`；激活态内阴影与图标色 `#06b6d4` / `text-cyan-400` → `#939b86` / `text-brand-400`。

**仍未清理（属 §8-3 明确延后的 chat/* 其余组件，本轮未整体重做）**：`ChatMessages`（青色气泡）、`ChatInput`（violet）、`ToolCallsCollapse`（sky/violet/indigo/cyan）、`ListingPanel`（cyan/violet/indigo），以及 `AgentTracePanel` / `AgentCapabilityPanel`（sky/violet）、`app/studio`（violet）。这些仍是暗色 + 青/紫视觉，若要让"去深蓝"真正全站一致，需单独一轮 chat/* 与 Studio 换色。
