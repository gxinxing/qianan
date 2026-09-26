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

        {/* 详情浮层扩展配置内容 */}
        <div className="pt-2 border-t border-[#e5e5e1] space-y-3 pb-6">
          {/* 提供商配置 (BYOK & MCP) */}
          {(selectedKey === "providers" || selectedKey === "default_model") && (
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
                保存配置
              </button>
            </div>
          )}

          {/* 判定核 (Judge) */}
          {selectedKey === "judge_kernel" && (
            <div className="bg-[#f0f5ee] border border-[#cbd9c3] rounded-xl p-3 space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-[#2d521d] flex items-center gap-1.5">
                  <ShieldCheck size={13} />
                  <span>判定核 (Judgment Kernel)</span>
                </span>
                <span className="text-[9.5px] px-1.5 py-0.5 rounded bg-white text-[#2d521d] border border-[#b2cca5] font-medium">
                  ACTIVE
                </span>
              </div>
              <p className="text-[10.5px] text-[#416330] leading-relaxed">
                轻量确定性判定核已启用，在输入、风险动作与完成度 35+ 个节点精准裁决。
              </p>
            </div>
          )}

          {/* 默认兜底面板 */}
          {selectedKey !== "providers" && selectedKey !== "default_model" && selectedKey !== "judge_kernel" && (
            <div className="bg-white border border-[#deded9] rounded-xl p-3 shadow-xs text-xs space-y-1 text-gray-500">
              <div className="font-semibold text-gray-700">配置节点已就绪</div>
              <p className="text-[11px]">该分类配置参数已同源链接至千岸 Agent 运行时。</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
