/** 千岸对话式 Agent 前端 — 类型定义 */

export interface ToolCall {
  id: string;
  name: string;
  input?: Record<string, unknown>;
  status: "running" | "completed" | "error";
  result?: string;
  isError?: boolean;
}

export type ContentBlock =
  | { type: "text"; text: string }
  | { type: "tool_use"; toolCall: ToolCall };

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  model?: string;
  timestamp: number;
  isStreaming?: boolean;
  toolCalls?: ToolCall[];
  contentBlocks?: ContentBlock[];
}

export interface Session {
  id: string;
  title: string;
  model: string;
  createdAt: number;
  messages: Message[];
}

/** 后端 listing 事件中的单个平台产物 */
export interface ListingItem {
  platform: string;
  display_name: string;
  title: string;
  bullets: string[];
  description: string;
  images: string[];
  detail_images?: string[];
  video_url?: string | null;
  compliance_passed: boolean;
  revised_count: number;
  compliance_errors: number;
  compliance_warns: number;
}

/** 后端 listing 事件快照 */
export interface ListingSnapshot {
  status: string;
  stage: string;
  progress: number;
  plan: {
    strategy: string;
    heal_budget: number;
    focus: string;
    research_tools: string[];
    decided_by: string;
  } | null;
  memory_recall: Array<{ lesson: string; platform: string; hit_count: number; source_task: string }>;
  reflections: Array<{ platform: string; lesson: string }>;
  listings: ListingItem[];
}

/** SSE 事件联合类型 */
export type SSEEvent =
  | { type: "init"; task_id: string }
  | { type: "trace"; phase: string; tool: string; args: string; result: string; status: string }
  | { type: "listing" } & ListingSnapshot
  | { type: "done"; task_id: string; status: string }
  | { type: "error"; message: string };

/** 工具元数据 */
export const TOOL_META: Record<string, { label: string; icon: string; color: string }> = {
  understand_product: { label: "商品理解", icon: "Eye", color: "#722ed1" },
  submit_plan: { label: "提交策略", icon: "ClipboardCheck", color: "#1890ff" },
  generate_listing: { label: "生成文案", icon: "PenLine", color: "#fa8c16" },
  review_listing: { label: "合规审核", icon: "ShieldCheck", color: "#52c41a" },
  revise_listing: { label: "修订文案", icon: "Edit3", color: "#faad14" },
  generate_images: { label: "生成图片", icon: "Image", color: "#f5222d" },
  generate_video: { label: "生成视频", icon: "Video", color: "#eb2f96" },
  submit_deliverable: { label: "交付", icon: "Check", color: "#52c41a" },
  recall_memory: { label: "记忆召回", icon: "Brain", color: "#13c2c2" },
  self_reflect: { label: "反思蒸馏", icon: "Sparkles", color: "#13c2c2" },
  finish: { label: "完成", icon: "Check", color: "#52c41a" },
};

export function getToolMeta(name: string) {
  return TOOL_META[name] || { label: name, icon: "Wrench", color: "#888" };
}

export function phaseLabel(phase: string) {
  const map: Record<string, string> = {
    plan: "规划",
    build: "生成",
    heal: "自愈",
    reflect: "反思",
    evolve: "进化",
  };
  return map[phase] || phase;
}
