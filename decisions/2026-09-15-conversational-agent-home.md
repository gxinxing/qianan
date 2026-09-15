## Decision: 首页作为唯一的对话式 Agent 工作区
## Context: 首页此前使用 `/api/generate` 后跳转结果页，另有 `/studio` 使用 `/api/chat`，两套界面和交互割裂；线上生产包还被 `.env.local` 覆盖为 localhost API。
## Alternatives considered: 保留首页任务表单并美化跳转；只重绘旧 Studio；把真实 SSE 对话、会话历史和实时产物统一到首页。
## Reasoning: 评审者从首页即可输入、查看 Agent 规划与工具步骤、继续追问并观察产物，能直接证明产品是对话式 Agent。复用现有 `/api/chat` 和任务产物协议，改动集中且无需重写后端。
## Trade-offs accepted: 原首页长营销内容退出首屏；`/studio` 重定向首页；会话历史仍保存在浏览器本地，历史会话不持久化产物快照。
