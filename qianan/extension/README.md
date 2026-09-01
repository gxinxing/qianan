# 千岸 QianAn Copilot — Chrome 侧边栏扩展（演示）

千岸 Copilot 的浏览器扩展形态：嵌在卖家后台（或 mock 演示页）旁边的侧边栏，
对当前上架表单做**合规体检**与**示例填充**。完整对话式流程（体检 / 算利润 /
生成上架内容并回填）见 Web 版 `/copilot` 页面。

## 加载方式（Chrome ≥116）

1. 打开 `chrome://extensions`
2. 右上角打开「开发者模式」
3. 点「加载已解压的扩展程序」，选择本 `extension/` 目录
4. 确认千岸后端在跑：`cd server && uvicorn app.main:app --port 8001`
5. 打开演示页 `http://localhost:3000/mock-seller-central.html`（或 `/copilot`）
6. 点浏览器工具栏的千岸图标 → 侧边栏打开 → 「填充示例」→「体检当前表单」

## 文件说明

| 文件 | 作用 |
| --- | --- |
| `manifest.json` | MV3 清单：side_panel + content_scripts |
| `background.js` | 点击图标即打开侧边栏 |
| `content.js` | 注入页面：按 `data-sc-field` 协议读表单 / 回填 |
| `sidepanel.html/js` | 瘦版侧边栏：体检、填充示例、跳转完整工作台 |

## 协议

- `QA_READ` → `{ type: "QA_FIELDS", payload: 表单字段 }`
- `QA_FILL`（payload）→ `{ type: "QA_FILLED", payload: { filled: n } }`

## 边界（演示范围）

- 只在声明匹配的页面注入（mock 演示页 + Amazon 卖家后台域名）；
- 只读表单与按确认回填，不触碰提交/发布按钮 —— 真实写操作走平台官方 API（Roadmap）。
