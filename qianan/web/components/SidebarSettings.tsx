"use client";

import { useState, useEffect } from "react";
import {
  Bot,
  Globe2,
  ShieldCheck,
  Truck,
  Lock,
  Sliders,
  Check,
  KeyRound,
  ArrowLeft,
  Sparkles,
  Copy,
  Terminal,
  Cpu,
  Layers,
  Archive,
  Info,
  Wrench,
  Compass,
} from "lucide-react";
import { API_BASE, PLATFORM_META } from "@/lib/api";

interface SidebarSettingsProps {
  onBack: () => void;
  platforms: string[];
  setPlatforms: React.Dispatch<React.SetStateAction<string[]>>;
  byokKey: string;
  setByokKey: (key: string) => void;
  byokImgKey: string;
  setByokImgKey: (key: string) => void;
  onSaveByok: () => void;
  confidentialMode: boolean;
  setConfidentialMode: (enabled: boolean) => void;
}

type CategoryKey = "preference" | "model" | "kernel" | "decision" | "capacity" | "system";

interface MenuItem {
  key: string;
  label: string;
  icon: typeof Bot;
  category: CategoryKey;
}

const CATEGORIES: Array<{ key: CategoryKey; label: string }> = [
  { key: "preference", label: "偏好" },
  { key: "model", label: "模型" },
  { key: "kernel", label: "内核" },
  { key: "decision", label: "判定点" },
  { key: "capacity", label: "能力" },
  { key: "system", label: "系统" },
];

const MENU_ITEMS: MenuItem[] = [
  // 偏好
  { key: "appearance", label: "外观", icon: Sliders, category: "preference" },
  { key: "system_pref", label: "系统", icon: Sliders, category: "preference" },
  { key: "chat_pref", label: "对话", icon: Bot, category: "preference" },
  // 模型
  { key: "providers", label: "提供商", icon: Globe2, category: "model" },
  { key: "default_model", label: "默认模型", icon: Cpu, category: "model" },
  // 内核
  { key: "judge_kernel", label: "判定器 (Judge)", icon: ShieldCheck, category: "kernel" },
  { key: "features", label: "功能特性", icon: Sliders, category: "kernel" },
  // 判定点
  { key: "dec_input", label: "输入", icon: ArrowLeft, category: "decision" },
  { key: "dec_context", label: "上下文", icon: Layers, category: "decision" },
  { key: "dec_memory", label: "经验库", icon: Sparkles, category: "decision" },
  { key: "dec_tools", label: "工具与安全", icon: Lock, category: "decision" },
  { key: "dec_turn", label: "回合", icon: Sliders, category: "decision" },
  { key: "dec_swarm", label: "协作 (Swarm)", icon: Bot, category: "decision" },
  // 能力
  { key: "skills", label: "技能", icon: Sparkles, category: "capacity" },
  { key: "tools", label: "工具", icon: Wrench, category: "capacity" },
  { key: "assistants", label: "助手", icon: Bot, category: "capacity" },
  { key: "browser", label: "应用内浏览器", icon: Compass, category: "capacity" },
  // 系统
  { key: "archived", label: "已归档的对话", icon: Archive, category: "system" },
  { key: "about", label: "关于千岸 Agent", icon: Info, category: "system" },
];

export default function SidebarSettings({
  onBack,
  platforms,
  setPlatforms,
  byokKey,
  setByokKey,
  byokImgKey,
  setByokImgKey,
  onSaveByok,
  confidentialMode,
  setConfidentialMode,
}: SidebarSettingsProps) {
  const [selectedKey, setSelectedKey] = useState<string>("providers");
  const [thinkingLevel, setThinkingLevel] = useState("medium");
  const [connMode, setConnMode] = useState<"mcp" | "auto" | "gateway">("mcp");
  const [copiedMcp, setCopiedMcp] = useState(false);
  const [detectedInfo, setDetectedInfo] = useState<{
    auto_detected?: boolean;
    has_bailian_key?: boolean;
    has_dashscope_key?: phenomenon;
    text_model?: string;
    image_model?: string;
    mcp_command?: string;
    server_dir?: string;
    mcp_snippet?: { mcpServers: Record<string, unknown> };
  } | null>(null);
  const [detecting, setDetecting] = useState(false);

  type phenomenon = boolean;

  const handleDetect = async () => {
    setDetecting(true);
    try {
      const res = await fetch(`${API_BASE}/api/config/detect`);
      if (res.ok) {
        const data = await res.json();
        setDetectedInfo(data);
      }
    } catch {
      // 容错兜底
    } finally {
      setDetecting(false);
    }
  };

  const mcpConfigText = JSON.stringify(
    detectedInfo?.mcp_snippet || {
      mcpServers: {
        qianan: {
          command: "python",
          args: ["-m", "app.mcp_server"],
          cwd: detectedInfo?.server_dir || "/path/to/qianan/server",
        },
      },
    },
    null,
    2
  );

  const copyMcpConfig = () => {
    navigator.clipboard.writeText(mcpConfigText);
    setCopiedMcp(true);
    setTimeout(() => setCopiedMcp(false), 2000);
  };

  useEffect(() => {
    if (typeof window !== "undefined") {
      const savedThinking = localStorage.getItem("qianan_thinking_level");
      if (savedThinking) setThinkingLevel(savedThinking);
    }
  }, []);

  return (
    <div className="flex flex-col h-full text-[#252525] bg-[#fafaf8]">
      {/* 头部标题与返回按钮 */}
      <div className="flex items-center justify-between pb-3 mb-2 border-b border-[#e5e5e1] flex-none px-2 pt-2">
        <div className="flex items-center gap-1.5 font-semibold text-xs text-[#272824]">
          <Sliders size={14} className="text-[#5e6752]" />
          <span>千岸 Agent 设置</span>
        </div>
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1 text-[11px] text-[#6f6f69] hover:text-[#252525] bg-white hover:bg-[#ecece8] px-2 py-1 rounded-md border border-[#deded9] transition-colors"
        >
          <ArrowLeft size={12} />
          <span>返回聊天</span>
        </button>
      </div>

      {/* 垂直分层多分类侧边导航 (对齐 mu 原生系统结构) */}
      <div className="flex-1 overflow-y-auto space-y-3 px-2 text-xs">
        {CATEGORIES.map((cat) => {
          const catItems = MENU_ITEMS.filter((item) => item.category === cat.key);
          if (catItems.length === 0) return null;
          return (
            <div key={cat.key} className="space-y-1">
              <div className="text-[10px] font-semibold text-[#858580] uppercase tracking-wider px-2 py-0.5">
                {cat.label}
              </div>
              <div className="space-y-0.5">
                {catItems.map((item) => {
                  const Icon = item.icon;
                  const isSelected = selectedKey === item.key;
                  return (
                    <button
                      key={item.key}
                      type="button"
                      onClick={() => setSelectedKey(item.key)}
                      className={`w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-left transition-all ${
                        isSelected
                          ? "bg-white text-[#272824] font-semibold shadow-xs border border-[#deded9]"
                          : "text-[#64645e] hover:text-[#252525] hover:bg-[#ecece8]"
                      }`}
                    >
                      <Icon size={14} className={isSelected ? "text-[#5e6752]" : "text-[#858580]"} />
                      <span className="text-[11px]">{item.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}

        {/* 详情浮层扩展配置内容：根据 selectedKey 渲染真实交互功能 */}
        <div className="pt-2 border-t border-[#e5e5e1] space-y-3 pb-6">
          {/* 外观 / 偏好 */}
          {(selectedKey === "appearance" || selectedKey === "system_pref" || selectedKey === "chat_pref") && (
            <div className="space-y-3">
              <div className="bg-white border border-[#deded9] rounded-xl p-3 shadow-xs space-y-2">
                <span className="text-[11px] font-semibold text-[#414638] block">主题与工作区外观</span>
                <div className="grid grid-cols-2 gap-1.5">
                  <button type="button" className="p-2 border border-[#5e6752] bg-[#f0f2eb] rounded-lg text-center text-xs font-medium">
                    极简纸色 (Default)
                  </button>
                  <button type="button" className="p-2 border border-[#deded9] bg-white rounded-lg text-center text-xs text-gray-500 hover:bg-gray-50">
                    暗黑极客 (Dark)
                  </button>
                </div>
              </div>
              <div className="bg-white border border-[#deded9] rounded-xl p-3 shadow-xs space-y-2">
                <span className="text-[11px] font-semibold text-[#414638] block">思考与推理深度 (Thinking Level)</span>
                <div className="grid grid-cols-3 gap-1">
                  {[
                    { key: "high", label: "深入思考" },
                    { key: "medium", label: "标准运营" },
                    { key: "low", label: "极速出稿" },
                  ].map((lvl) => (
                    <button
                      key={lvl.key}
                      type="button"
                      onClick={() => {
                        setThinkingLevel(lvl.key);
                        localStorage.setItem("qianan_thinking_level", lvl.key);
                      }}
                      className={`p-1.5 border text-center text-[10.5px] rounded-md transition-colors ${
                        thinkingLevel === lvl.key
                          ? "border-[#5e6752] bg-[#f0f2eb] font-semibold text-[#272824]"
                          : "border-[#deded9] bg-white text-gray-500"
                      }`}
                    >
                      {lvl.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* 模型 / 提供商 */}
          {(selectedKey === "providers" || selectedKey === "default_model") && (
            <div className="space-y-3">
              <div className="bg-white border border-[#deded9] rounded-xl p-3 shadow-xs space-y-2">
                <span className="text-[11px] font-semibold text-[#414638] block">API Token 凭证</span>
                <input
                  type="password"
                  value={byokKey}
                  onChange={(e) => setByokKey(e.target.value)}
                  placeholder="千岸统一 API Token (sk-...)"
                  className="w-full bg-[#fcfcfb] border border-[#deded9] rounded-lg px-2.5 py-1.5 text-xs text-[#252525] outline-none font-mono placeholder:text-[#a0a09a]"
                />
                <button
                  type="button"
                  onClick={onSaveByok}
                  className="w-full py-1.5 rounded-lg bg-[#272824] hover:bg-[#414638] text-white text-xs font-medium transition-colors"
                >
                  保存 API Token
                </button>
              </div>

              {/* 大模型接入模式分栏：MCP / 本地自适应 */}
              <div className="bg-white border border-[#deded9] rounded-xl p-3 shadow-xs space-y-2">
                <span className="text-[11px] font-semibold text-[#414638] block">MCP 协议与环境探测</span>
                <button
                  type="button"
                  onClick={handleDetect}
                  disabled={detecting}
                  className="w-full py-1.5 rounded-lg border border-[#deded9] hover:bg-[#f0f2eb] text-xs font-medium flex items-center justify-center gap-1.5 transition-colors"
                >
                  <Cpu size={13} />
                  <span>{detecting ? "探测中..." : "一键探测本机大模型环境"}</span>
                </button>
                {detectedInfo && (
                  <div className="p-2 rounded-lg bg-[#f0f5ee] border border-[#cbd9c3] text-[10px] text-[#2d521d] space-y-0.5">
                    <div>✓ 文本模型: {detectedInfo.text_model || "Qwen3.7-Max"}</div>
                    <div>✓ 视觉模型: {detectedInfo.image_model || "Wan2.7-Image"}</div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 内核 / 判定器 */}
          {(selectedKey === "judge_kernel" || selectedKey === "features") && (
            <div className="space-y-3">
              <div className="bg-[#f0f5ee] border border-[#cbd9c3] rounded-xl p-3 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-[#2d521d] flex items-center gap-1.5">
                    <ShieldCheck size={13} />
                    <span>判定核 (Judgment Kernel)</span>
                  </span>
                  <span className="text-[9.5px] px-1.5 py-0.5 rounded bg-white text-[#2d521d] border border-[#b2cca5] font-semibold">
                    ACTIVE
                  </span>
                </div>
                <p className="text-[10.5px] text-[#416330] leading-relaxed">
                  判定核已挂载：在 input.preflight / tool.risk / turn.completion 等 35+ 个节点触发确定性裁决。
                </p>
              </div>

              <div className="bg-white border border-[#deded9] rounded-xl p-3 shadow-xs space-y-2">
                <span className="text-[11px] font-semibold text-[#414638] block">合规审查严格度</span>
                <select className="w-full bg-[#fcfcfb] border border-[#deded9] rounded-lg px-2.5 py-1.5 text-xs text-[#252525] outline-none">
                  <option value="strict">严苛防封店模式 (47 项全开 · 阻断级自动回炉)</option>
                  <option value="standard">标准运营模式 (拦截绝对化用语与溢出)</option>
                </select>
              </div>
            </div>
          )}

          {/* 判定点 (Decision Points: input, context, memory, tools, turn, swarm) */}
          {selectedKey.startsWith("dec_") && (
            <div className="space-y-3">
              <div className="bg-white border border-[#deded9] rounded-xl p-3 shadow-xs space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-[#414638] capitalize">
                    判定点裁决配置: {selectedKey.replace("dec_", "")}
                  </span>
                  <span className="text-[9.5px] text-[#5e6752] font-mono bg-[#f0f2eb] px-1.5 py-0.5 rounded">
                    Mode: Active
                  </span>
                </div>
                <div className="text-[10.5px] text-gray-600 leading-relaxed">
                  {selectedKey === "dec_input" && "input.preflight：评估输入请求格式、思考级别与目标平台覆盖。"}
                  {selectedKey === "dec_context" && "context.compact：动态判断产物上下文膨胀度，只把必须的信息拉入 Prompt。"}
                  {selectedKey === "dec_memory" && "memory.recall：从 Evolution Agent 沉淀库中自动召回店铺 SOP 历史教训。"}
                  {selectedKey === "dec_tools" && "tool.risk：监测输出中是否包含医疗宣称、极端的绝对化营销词汇。"}
                  {selectedKey === "dec_turn" && "turn.completion：交付闸门判定，确定性验证平台全覆盖与零 blocker。"}
                  {selectedKey === "dec_swarm" && "swarm.routing：Supervisor 在共享黑板上进行基于 Worker 能力竞选的任务派发。"}
                </div>
              </div>
            </div>
          )}

          {/* 能力 (Skills, Tools, Assistants, Browser) */}
          {(selectedKey === "skills" || selectedKey === "tools" || selectedKey === "assistants" || selectedKey === "browser") && (
            <div className="space-y-3">
              <div className="bg-white border border-[#deded9] rounded-xl p-3 shadow-xs space-y-2">
                <span className="text-[11px] font-semibold text-[#414638] block">目标平台集成 ({platforms.length}/5)</span>
                <div className="space-y-1">
                  {PLATFORM_META.map((p) => {
                    const isSelected = platforms.includes(p.key);
                    return (
                      <div
                        key={p.key}
                        onClick={() => {
                          setPlatforms((cur) =>
                            isSelected ? cur.filter((k) => k !== p.key) : [...cur, p.key]
                          );
                        }}
                        className={`flex items-center justify-between p-2 rounded-lg border cursor-pointer text-xs transition-colors ${
                          isSelected
                            ? "border-[#bdc4b1] bg-[#f0f2eb] text-[#272824] font-medium"
                            : "border-[#e5e5e1] bg-white text-[#73736c]"
                        }`}
                      >
                        <span>{p.name}</span>
                        {isSelected && <Check size={14} className="text-[#5e6752]" />}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* 系统 (Archived, About) */}
          {(selectedKey === "archived" || selectedKey === "about") && (
            <div className="space-y-3">
              <div className="bg-white border border-[#deded9] rounded-xl p-3 shadow-xs flex items-center justify-between">
                <div>
                  <span className="text-[11px] font-semibold text-[#272824] block flex items-center gap-1.5">
                    <Lock size={12} className="text-[#059669]" />
                    <span>机密上新：用后即焚</span>
                  </span>
                  <span className="text-[10px] text-[#73736c]">
                    任务导出后物理擦除服务端临时存储
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={confidentialMode}
                  onChange={(e) => {
                    setConfidentialMode(e.target.checked);
                    localStorage.setItem("qianan_confidential_mode", e.target.checked ? "1" : "0");
                  }}
                  className="accent-[#5e6752] w-4 h-4 cursor-pointer"
                />
              </div>

              <div className="bg-[#fafaf8] border border-[#e5e5e1] rounded-xl p-3 space-y-1.5 text-[10.5px] text-[#64645e]">
                <div className="font-semibold text-[#272824]">关于千岸 Agent v2.0</div>
                <p className="leading-relaxed">基于 mu (qybaihe/mu) 设计哲学构建的智能跨境上新与自进化 Agent。</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
