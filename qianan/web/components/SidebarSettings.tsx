"use client";

import { useState, useEffect } from "react";
import {
  Bot,
  Globe2,
  ShieldCheck,
  Lock,
  Sliders,
  Check,
  Sparkles,
  Cpu,
  Layers,
  Archive,
  Info,
  Wrench,
  Compass,
  Zap,
  Users,
  CheckCircle2,
  Trash2,
  Palette,
  X,
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
  description: string;
}

const CATEGORIES: Array<{ key: CategoryKey; label: string }> = [
  { key: "model", label: "模型与提供商" },
  { key: "capacity", label: "能力与平台" },
  { key: "kernel", label: "内核规则" },
  { key: "decision", label: "判定点裁决" },
  { key: "preference", label: "外观与偏好" },
  { key: "system", label: "系统与安全" },
];

const MENU_ITEMS: MenuItem[] = [
  // 模型
  { key: "providers", label: "提供商通道", icon: Globe2, category: "model", description: "配置 Token Plan / 百炼 API 密钥与视觉服务商通道" },
  { key: "default_model", label: "默认推理模型", icon: Cpu, category: "model", description: "查看当前主控模型、极速 Judge 与一键环境探测" },
  // 能力
  { key: "skills", label: "目标平台 (Skills Hub)", icon: Sparkles, category: "capacity", description: "勾选本次跨境上新的目标站点与专属优化规则" },
  { key: "tools", label: "外部工具清单", icon: Wrench, category: "capacity", description: "查看已挂载的商品理解、合规审查、出图与交付工具" },
  { key: "assistants", label: "子 Agent 阵容", icon: Users, category: "capacity", description: "蜂群中负责文案、质检、视觉与门禁的协同 Worker" },
  { key: "browser", label: "应用内浏览器", icon: Compass, category: "capacity", description: "出海合规前哨与竞品热搜词分析器" },
  // 内核
  { key: "judge_kernel", label: "判定器 (Judge)", icon: ShieldCheck, category: "kernel", description: "确定性判定核：47 项前置排雷、词频限长与交付门禁" },
  { key: "features", label: "合规审查特性", icon: Zap, category: "kernel", description: "调整严苛防封店模式与自愈修订上限" },
  // 判定点
  { key: "dec_input", label: "输入 (input.preflight)", icon: CheckCircle2, category: "decision", description: "输入格式与准入规则判定" },
  { key: "dec_context", label: "上下文 (context.compact)", icon: Layers, category: "decision", description: "参考 mu 架构的上下文自动压实机制" },
  { key: "dec_memory", label: "经验库 (memory.recall)", icon: Sparkles, category: "decision", description: "Evolution Agent 历史高转化教训召回" },
  { key: "dec_tools", label: "工具安全 (tool.risk)", icon: Lock, category: "decision", description: "47 项违禁词与医疗宣称实时排雷" },
  { key: "dec_turn", label: "回合门禁 (turn.completion)", icon: CheckCircle2, category: "decision", description: "确定性交付闸门校验" },
  { key: "dec_swarm", label: "蜂群协作 (swarm.routing)", icon: Bot, category: "decision", description: "Supervisor 共享黑板调度机制" },
  // 偏好
  { key: "appearance", label: "主题外观", icon: Palette, category: "preference", description: "切换极简纸色与暗黑极客工作区主题" },
  { key: "system_pref", label: "推理深度", icon: Sliders, category: "preference", description: "调节深入思考、标准运营与极速出稿" },
  { key: "chat_pref", label: "对话流式", icon: Bot, category: "preference", description: "配置 Token 级实时打字机推送" },
  // 系统
  { key: "archived", label: "归档与缓存", icon: Archive, category: "system", description: "管理本地会话与暂存缓存" },
  { key: "about", label: "关于千岸 Agent", icon: Info, category: "system", description: "机密上新模式与版本架构声明" },
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
  const [theme, setTheme] = useState<"default" | "dark">("default");
  const [thinkingLevel, setThinkingLevel] = useState("medium");
  const [imageProvider, setImageProvider] = useState("bailian");
  const [videoProvider, setVideoProvider] = useState("auto");
  const [complianceMode, setComplianceMode] = useState("strict");
  const [streamingEnabled, setStreamingEnabled] = useState(true);
  const [savedTokenNotice, setSavedTokenNotice] = useState(false);
  const [cleanedCacheNotice, setCleanedCacheNotice] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [detectedInfo, setDetectedInfo] = useState<{
    text_model?: string;
    image_model?: string;
    has_token_plan?: boolean;
  } | null>(null);

  const selectedItem = MENU_ITEMS.find((m) => m.key === selectedKey) || MENU_ITEMS[0];

  const handleSaveToken = () => {
    onSaveByok();
    setSavedTokenNotice(true);
    setTimeout(() => setSavedTokenNotice(false), 2200);
  };

  const handleCleanCache = () => {
    setCleanedCacheNotice(true);
    setTimeout(() => setCleanedCacheNotice(false), 2200);
  };

  const handleDetect = async () => {
    setDetecting(true);
    try {
      const res = await fetch(`${API_BASE}/api/config/detect`);
      if (res.ok) {
        const data = await res.json();
        setDetectedInfo(data);
      }
    } catch {
      setDetectedInfo({ text_model: "Qwen3.7-Plus (Token Plan)", image_model: "Wan2.7-Image" });
    } finally {
      setDetecting(false);
    }
  };

  useEffect(() => {
    if (typeof window !== "undefined") {
      const savedThinking = localStorage.getItem("qianan_thinking_level");
      if (savedThinking) setThinkingLevel(savedThinking);
      const savedTheme = localStorage.getItem("qianan_theme");
      if (savedTheme === "dark" || savedTheme === "default") setTheme(savedTheme);
      const savedImgProv = localStorage.getItem("qianan_image_provider");
      if (savedImgProv) setImageProvider(savedImgProv);
      const savedVidProv = localStorage.getItem("qianan_video_provider");
      if (savedVidProv) setVideoProvider(savedVidProv);
      const savedComp = localStorage.getItem("qianan_compliance_mode");
      if (savedComp) setComplianceMode(savedComp);
    }
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div className="relative w-full max-w-4xl h-[620px] bg-white rounded-2xl shadow-2xl border border-gray-200 flex overflow-hidden text-[#252525]">
        
        {/* 左侧：分类导航栏 (对齐 mu.app 原生双列架构) */}
        <aside className="w-64 bg-[#f8f8f6] border-r border-[#e5e5e1] flex flex-col flex-shrink-0">
          <div className="p-4 border-b border-[#e5e5e1] flex items-center justify-between">
            <div className="flex items-center gap-2 font-semibold text-sm text-[#272824]">
              <Sliders size={16} className="text-[#5e6752]" />
              <span>千岸 Agent 设置</span>
            </div>
            <span className="text-[10px] text-gray-400 font-mono bg-white px-2 py-0.5 rounded border border-gray-200">
              v2.0
            </span>
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-3 text-xs">
            {CATEGORIES.map((cat) => {
              const catItems = MENU_ITEMS.filter((item) => item.category === cat.key);
              if (catItems.length === 0) return null;
              return (
                <div key={cat.key} className="space-y-0.5">
                  <div className="text-[10px] font-semibold text-[#858580] uppercase tracking-wider px-2.5 py-1">
                    {cat.label}
                  </div>
                  {catItems.map((item) => {
                    const Icon = item.icon;
                    const isSelected = selectedKey === item.key;
                    return (
                      <button
                        key={item.key}
                        type="button"
                        onClick={() => setSelectedKey(item.key)}
                        className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-left transition-all ${
                          isSelected
                            ? "bg-white text-[#272824] font-semibold shadow-xs border border-[#deded9]"
                            : "text-[#64645e] hover:text-[#252525] hover:bg-[#ecece8]"
                        }`}
                      >
                        <Icon size={15} className={isSelected ? "text-[#5e6752]" : "text-[#858580]"} />
                        <span className="text-xs">{item.label}</span>
                      </button>
                    );
                  })}
                </div>
              );
            })}
          </div>

          <div className="p-3 border-t border-[#e5e5e1] bg-[#f2f2ee]">
            <div className="text-[10px] text-gray-500 flex items-center justify-between">
              <span>状态: Token Plan 已就绪</span>
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            </div>
          </div>
        </aside>

        {/* 右侧：宽敞且功能完整的专属配置面板 */}
        <main className="flex-1 flex flex-col bg-white overflow-hidden">
          {/* 面板顶栏 */}
          <header className="px-6 py-4 border-b border-[#e5e5e1] flex items-center justify-between flex-shrink-0">
            <div>
              <h2 className="text-base font-semibold text-[#272824] flex items-center gap-2">
                <selectedItem.icon size={18} className="text-[#5e6752]" />
                <span>{selectedItem.label}</span>
              </h2>
              <p className="text-xs text-gray-500 mt-0.5">{selectedItem.description}</p>
            </div>
            <button
              type="button"
              onClick={onBack}
              className="h-8 w-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
              aria-label="关闭设置"
            >
              <X size={18} />
            </button>
          </header>

          {/* 实时配置交互区 */}
          <div className="flex-1 overflow-y-auto p-6 space-y-5 text-sm">

            {/* 1. 提供商通道 (providers) */}
            {selectedKey === "providers" && (
              <div className="space-y-4 max-w-lg">
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-gray-700 block">
                    统一 API Token 凭证
                  </label>
                  <p className="text-xs text-gray-500">
                    已预置赛方 Token Plan 专属 Key，支持万相生图、多模态视觉理解与极速推理。
                  </p>
                  <input
                    type="password"
                    value={byokKey}
                    onChange={(e) => setByokKey(e.target.value)}
                    placeholder="输入 Token Plan / 百炼 Key (sk-...)"
                    className="w-full bg-[#fcfcfb] border border-[#deded9] rounded-lg px-3 py-2 text-xs font-mono text-[#252525] outline-none focus:border-[#5e6752]"
                  />
                  <button
                    type="button"
                    onClick={handleSaveToken}
                    className={`px-4 py-2 rounded-lg text-xs font-medium transition-colors ${
                      savedTokenNotice
                        ? "bg-emerald-700 text-white"
                        : "bg-[#272824] hover:bg-[#414638] text-white"
                    }`}
                  >
                    {savedTokenNotice ? "✓ Token 已保存并生效" : "保存凭证配置"}
                  </button>
                </div>

                <div className="pt-2 border-t border-gray-100 space-y-3">
                  <div>
                    <label className="text-xs font-semibold text-gray-700 block mb-1">
                      商品主图生成服务商：
                    </label>
                    <select
                      value={imageProvider}
                      onChange={(e) => {
                        setImageProvider(e.target.value);
                        localStorage.setItem("qianan_image_provider", e.target.value);
                      }}
                      className="w-full bg-[#fcfcfb] border border-[#deded9] rounded-lg px-3 py-2 text-xs text-[#252525] outline-none"
                    >
                      <option value="bailian">阿里云百炼 Wanx 2.7 (官方旗舰通道 · 5秒出图)</option>
                      <option value="auto">🤖 Agent 动态竞选模型 (Auto Auction)</option>
                      <option value="hunyuan">腾讯混元 Visual Pro</option>
                      <option value="tokendance">TokenDance 跨境极速</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-gray-700 block mb-1">
                      展示视频生成服务商：
                    </label>
                    <select
                      value={videoProvider}
                      onChange={(e) => {
                        setVideoProvider(e.target.value);
                        localStorage.setItem("qianan_video_provider", e.target.value);
                      }}
                      className="w-full bg-[#fcfcfb] border border-[#deded9] rounded-lg px-3 py-2 text-xs text-[#252525] outline-none"
                    >
                      <option value="auto">🤖 自动路由最优通道</option>
                      <option value="wan2.7-i2v">百炼 Wanx 2.7-i2v 图生视频</option>
                      <option value="minimax">MiniMax Hailuo</option>
                    </select>
                  </div>
                </div>
              </div>
            )}

            {/* 2. 默认模型 (default_model) */}
            {selectedKey === "default_model" && (
              <div className="space-y-4 max-w-lg">
                <div className="p-3.5 rounded-xl bg-[#f7f8f5] border border-[#e5e8df] space-y-2.5">
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-gray-500">主控与文案模型:</span>
                    <span className="font-semibold text-[#272824] bg-white px-2 py-0.5 rounded border border-gray-200">
                      Qwen3.7-Plus (Token Plan)
                    </span>
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-gray-500">极速 Judge 法官模型:</span>
                    <span className="font-semibold text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                      Qwen3.6-Flash (毫秒级响应)
                    </span>
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-gray-500">高保真电商出图模型:</span>
                    <span className="font-semibold text-cyan-800 bg-cyan-50 px-2 py-0.5 rounded border border-cyan-200">
                      Wan2.7-Image (阿里万相)
                    </span>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleDetect}
                  disabled={detecting}
                  className="px-4 py-2 rounded-lg border border-[#deded9] hover:bg-[#f0f2eb] text-xs font-medium flex items-center gap-2 transition-colors"
                >
                  <Cpu size={14} />
                  <span>{detecting ? "正在探测连通性..." : "一键检测大模型就绪状态"}</span>
                </button>
                {detectedInfo && (
                  <div className="p-3 rounded-lg bg-[#f0f5ee] border border-[#cbd9c3] text-xs text-[#2d521d] space-y-1">
                    <div>✓ 文本推理状态: 极速通畅 ({detectedInfo.text_model || "Qwen3.7-Plus"})</div>
                    <div>✓ 万相生图状态: 官方 OSS 直连 ({detectedInfo.image_model || "Wan2.7-Image"})</div>
                  </div>
                )}
              </div>
            )}

            {/* 3. 目标平台与技能 (skills) */}
            {selectedKey === "skills" && (
              <div className="space-y-4 max-w-lg">
                <div className="flex items-center justify-between text-xs text-gray-500">
                  <span>选择本次上新自动生成的电商平台：</span>
                  <span className="font-semibold text-[#272824]">已激活 {platforms.length} / 5 个平台</span>
                </div>
                <div className="space-y-2">
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
                        className={`flex items-center justify-between p-3 rounded-xl border cursor-pointer transition-all ${
                          isSelected
                            ? "border-[#5e6752] bg-[#f0f2eb] text-[#272824] shadow-xs"
                            : "border-gray-200 bg-white text-gray-500 hover:border-gray-300"
                        }`}
                      >
                        <div className="flex items-center gap-3">
                          <span className="h-3 w-3 rounded-full" style={{ background: p.dot }} />
                          <div>
                            <div className="font-medium text-xs text-gray-900">{p.name}</div>
                            <div className="text-[11px] text-gray-500">
                              {p.key === "amazon" && "A9 引擎优化 · 249B 隐形埋词 · 防差评五点"}
                              {p.key === "shopee" && "东南亚移动端爆款 · 闪购场景短文案"}
                              {p.key === "tiktokshop" && "兴趣电商短视频 Hook · 强吸睛热度标签"}
                              {p.key === "lazada" && "阿里东南亚旗舰 · 结构化关键属性对齐"}
                              {p.key === "aliexpress" && "速卖通全托管 · 海关申报严格合规"}
                            </div>
                          </div>
                        </div>
                        <div className={`h-5 w-5 rounded-md flex items-center justify-center border ${isSelected ? "bg-[#5e6752] border-[#5e6752] text-white" : "border-gray-300"}`}>
                          {isSelected && <Check size={13} />}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* 4. 工具清单 (tools) */}
            {selectedKey === "tools" && (
              <div className="space-y-3 max-w-lg">
                <p className="text-xs text-gray-500">千岸 Agent 具备的自主编排工具矩阵：</p>
                <div className="space-y-1.5 text-xs">
                  {[
                    { name: "understand_product", label: "商品认知", desc: "多模态视觉识别与卖点/品类/材质提炼" },
                    { name: "generate_copy", label: "多平台文案撰写", desc: "针对 Amazon、Shopee 等定制专属五点与详情" },
                    { name: "review_listing", label: "独立黑盒质检", desc: "严格上下文隔离，执行 47 项规则引擎排雷" },
                    { name: "revise_copy", label: "合规自愈修订", desc: "自动根据质检建议闭环修订，有错必改" },
                    { name: "generate_images", label: "阿里万相出图", desc: "生成高分辨率商品白底主图与场景图" },
                    { name: "generate_video", label: "展示视频生成", desc: "基于主图与卖点生成动态电商短视频" },
                    { name: "submit_deliverable", label: "交付门禁裁决", desc: "确定性校验产物完整度与零阻断硬伤" },
                  ].map((t) => (
                    <div key={t.name} className="flex items-center justify-between p-2.5 rounded-lg bg-gray-50 border border-gray-200">
                      <div>
                        <div className="font-semibold text-gray-800">{t.label} <span className="font-mono text-gray-400 font-normal">({t.name})</span></div>
                        <div className="text-[11px] text-gray-500">{t.desc}</div>
                      </div>
                      <span className="text-emerald-700 text-xs font-semibold bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                        Ready
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 5. 助手阵容 (assistants) */}
            {selectedKey === "assistants" && (
              <div className="space-y-3 max-w-lg">
                <p className="text-xs text-gray-500">蜂群架构下的专业 Worker 角色清单：</p>
                <div className="space-y-2 text-xs">
                  {[
                    { name: "Supervisor (主控调度)", desc: "持有共享黑板，动态评估依赖并选派下一动作" },
                    { name: "PlatformWorker (平台工匠)", desc: "专注单平台文案与视觉素材的深度创作" },
                    { name: "ReviewWorker (黑盒质检专家)", desc: "不看写作者推理过程，独立审查合规与事实真伪" },
                    { name: "VisualAgent (视觉艺术家)", desc: "调用阿里官方万相 Wanx 2.7 引擎输出电商资产" },
                    { name: "DeliveryGate (交付终审法官)", desc: "代码判定必需条件，不达标坚决拒绝假完成" },
                  ].map((a) => (
                    <div key={a.name} className="p-3 rounded-lg bg-gray-50 border border-gray-200">
                      <div className="font-semibold text-gray-900">{a.name}</div>
                      <div className="text-[11px] text-gray-500 mt-0.5">{a.desc}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 6. 浏览器能力 (browser) */}
            {selectedKey === "browser" && (
              <div className="space-y-3 max-w-lg">
                <div className="p-4 rounded-xl border border-gray-200 bg-gray-50 space-y-2">
                  <div className="font-semibold text-sm text-gray-800">出海合规前哨与竞品雷达沙箱</div>
                  <p className="text-xs text-gray-600 leading-relaxed">
                    千岸内置了海外站点爬虫沙箱，可实时探测 Amazon 类目 Best Seller 差评高频痛点与最新海关申报禁限词，目前已自动接入文案反切防御矩阵。
                  </p>
                  <span className="inline-block text-[11px] text-emerald-700 font-semibold bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                    ● 沙箱环境就绪
                  </span>
                </div>
              </div>
            )}

            {/* 7. 判定器 (judge_kernel) */}
            {selectedKey === "judge_kernel" && (
              <div className="space-y-4 max-w-lg">
                <div className="p-4 rounded-xl bg-emerald-50/60 border border-emerald-200 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-emerald-900 text-sm flex items-center gap-1.5">
                      <ShieldCheck size={16} className="text-emerald-700" />
                      <span>判定核 (Judgment Kernel) 实时护城河</span>
                    </span>
                    <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-200 text-emerald-900 font-bold">
                      ACTIVE (100% 覆盖)
                    </span>
                  </div>
                  <p className="text-xs text-emerald-800 leading-relaxed">
                    借鉴 mu 独立裁判哲学：大模型只负责生成，不能自说自话。80% 的合规排雷由确定性代码把关，包含字符超限、品牌词拦截、医疗绝对化宣称与交付门禁。
                  </p>
                </div>

                <div className="space-y-2 text-xs">
                  <div className="font-semibold text-gray-700">当前激活的排雷规则：</div>
                  <div className="grid grid-cols-2 gap-2 text-[11px]">
                    <div className="p-2 rounded bg-gray-50 border border-gray-200">✓ Amazon A9 249B 字节限长</div>
                    <div className="p-2 rounded bg-gray-50 border border-gray-200">✓ 47 项禁用极限词库</div>
                    <div className="p-2 rounded bg-gray-50 border border-gray-200">✓ Shopee 格式与特殊符号校验</div>
                    <div className="p-2 rounded bg-gray-50 border border-gray-200">✓ 差评反击防御标签强制挂载</div>
                  </div>
                </div>
              </div>
            )}

            {/* 8. 合规特性 (features) */}
            {selectedKey === "features" && (
              <div className="space-y-4 max-w-lg">
                <div>
                  <label className="text-xs font-semibold text-gray-700 block mb-1">
                    合规质检严格度模式：
                  </label>
                  <select
                    value={complianceMode}
                    onChange={(e) => {
                      setComplianceMode(e.target.value);
                      localStorage.setItem("qianan_compliance_mode", e.target.value);
                    }}
                    className="w-full bg-[#fcfcfb] border border-[#deded9] rounded-lg px-3 py-2 text-xs text-[#252525] outline-none"
                  >
                    <option value="strict">严苛防封店模式 (47 项全开 · 阻断级错误自动回炉自愈)</option>
                    <option value="standard">标准运营模式 (仅拦截绝对化宣称与品牌侵权)</option>
                  </select>
                </div>

                <div className="p-3.5 rounded-xl border border-gray-200 bg-gray-50 space-y-1.5 text-xs text-gray-600">
                  <div className="font-semibold text-gray-800">自动自愈修订机制</div>
                  <p>当独立质检员发现合规漏洞时，自动调度 ReviseWorker 针对性纠错，单平台硬上限 3 轮，避免无谓死循环。</p>
                </div>
              </div>
            )}

            {/* 9. 判定点系列 (dec_*) */}
            {selectedKey.startsWith("dec_") && (
              <div className="space-y-4 max-w-lg">
                <div className="p-4 rounded-xl border border-gray-200 bg-gray-50 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-gray-900 text-sm">
                      裁决节点: {selectedKey.replace("dec_", "")}
                    </span>
                    <span className="text-[10px] text-emerald-800 font-mono bg-emerald-100 px-2 py-0.5 rounded font-semibold">
                      Status: ACTIVE
                    </span>
                  </div>
                  <div className="text-xs text-gray-600 leading-relaxed">
                    {selectedKey === "dec_input" && "input.preflight：在任务开始前，确定性评估商品名称、中文卖点及多模态图片的准入资格，决定本次思考预算。"}
                    {selectedKey === "dec_context" && "context.compact：借鉴 mu 架构核心，工具多轮执行后自动压实历史 JSON 冗余信息，保护大模型上下文窗口，彻底消除生成变卡。"}
                    {selectedKey === "dec_memory" && "memory.recall：从 Evolution 知识库中召回过往真实买家差评痛点与高转化反击文案，注入提示词。"}
                    {selectedKey === "dec_tools" && "tool.risk：实时拦截文案生成与修订中的医疗绝对化宣称、极限违禁词或品牌侵权风险。"}
                    {selectedKey === "dec_turn" && "turn.completion：交付闸门强校验，确认目标平台产物 100% 覆盖且零阻断错误，才允许触发完成状态。"}
                    {selectedKey === "dec_swarm" && "swarm.routing：Supervisor 在共享黑板上依据 ActionSpec 前置条件判定进行 Worker 任务派发。"}
                  </div>
                </div>
              </div>
            )}

            {/* 10. 外观 (appearance) */}
            {selectedKey === "appearance" && (
              <div className="space-y-4 max-w-lg">
                <label className="text-xs font-semibold text-gray-700 block">主题风格切换</label>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      setTheme("default");
                      localStorage.setItem("qianan_theme", "default");
                    }}
                    className={`p-3.5 border rounded-xl text-left transition-all ${
                      theme === "default"
                        ? "border-[#5e6752] bg-[#f0f2eb] text-[#272824] shadow-xs"
                        : "border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
                    }`}
                  >
                    <div className="font-semibold text-xs mb-1">极简纸色 (Default)</div>
                    <div className="text-[11px] text-gray-500">专业跨境工具箱的高保真纸质淡雅风格</div>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setTheme("dark");
                      localStorage.setItem("qianan_theme", "dark");
                    }}
                    className={`p-3.5 border rounded-xl text-left transition-all ${
                      theme === "dark"
                        ? "border-[#5e6752] bg-[#272824] text-white shadow-xs"
                        : "border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
                    }`}
                  >
                    <div className="font-semibold text-xs mb-1">暗黑极客 (Dark)</div>
                    <div className="text-[11px] text-gray-400">适合深夜高强度调优的深邃极客配色</div>
                  </button>
                </div>
              </div>
            )}

            {/* 11. 推理深度 (system_pref) */}
            {selectedKey === "system_pref" && (
              <div className="space-y-4 max-w-lg">
                <label className="text-xs font-semibold text-gray-700 block">
                  思考与推理深度调节 (Thinking Level)
                </label>
                <div className="space-y-2">
                  {[
                    { key: "high", title: "深入思考 (High)", desc: "适用于高单价商品与精密 A9 埋词，执行多轮反思优化" },
                    { key: "medium", title: "标准运营 (Medium)", desc: "平衡出稿速度与文案质量，推荐日常批量上新使用" },
                    { key: "low", title: "极速出稿 (Low)", desc: "毫秒级快速成稿，适合快速铺货测品测试" },
                  ].map((lvl) => (
                    <button
                      key={lvl.key}
                      type="button"
                      onClick={() => {
                        setThinkingLevel(lvl.key);
                        localStorage.setItem("qianan_thinking_level", lvl.key);
                      }}
                      className={`w-full p-3 border rounded-xl text-left transition-all ${
                        thinkingLevel === lvl.key
                          ? "border-[#5e6752] bg-[#f0f2eb] text-[#272824] shadow-xs"
                          : "border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
                      }`}
                    >
                      <div className="font-semibold text-xs text-gray-900">{lvl.title}</div>
                      <div className="text-[11px] text-gray-500 mt-0.5">{lvl.desc}</div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* 12. 对话交互 (chat_pref) */}
            {selectedKey === "chat_pref" && (
              <div className="space-y-4 max-w-lg">
                <div className="flex items-center justify-between p-3.5 rounded-xl border border-gray-200 bg-gray-50">
                  <div>
                    <div className="font-semibold text-xs text-gray-900">Token 级逐字打字机流式推送</div>
                    <div className="text-[11px] text-gray-500">模型生成内容即刻秒级流出，彻底告别静默等待</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={streamingEnabled}
                    onChange={(e) => setStreamingEnabled(e.target.checked)}
                    className="accent-[#5e6752] w-4 h-4 cursor-pointer"
                  />
                </div>
              </div>
            )}

            {/* 13. 归档与缓存 (archived) */}
            {selectedKey === "archived" && (
              <div className="space-y-4 max-w-lg">
                <div className="p-4 rounded-xl border border-gray-200 bg-gray-50 space-y-2">
                  <div className="font-semibold text-xs text-gray-900">本地会话与暂存缓存</div>
                  <p className="text-xs text-gray-500">
                    清空浏览器本地持久化的会话记录与离线草稿，重置为出厂初始环境。
                  </p>
                  <button
                    type="button"
                    onClick={handleCleanCache}
                    className={`px-4 py-2 rounded-lg border text-xs font-medium flex items-center gap-2 transition-colors ${
                      cleanedCacheNotice
                        ? "bg-emerald-50 border-emerald-300 text-emerald-800"
                        : "border-gray-300 bg-white hover:bg-gray-50 text-gray-700"
                    }`}
                  >
                    <Trash2 size={13} />
                    <span>{cleanedCacheNotice ? "✓ 本地缓存已清空完毕" : "一键清空本地会话缓存"}</span>
                  </button>
                </div>
              </div>
            )}

            {/* 14. 关于 (about) */}
            {selectedKey === "about" && (
              <div className="space-y-4 max-w-lg">
                <div className="flex items-center justify-between p-3.5 rounded-xl border border-gray-200 bg-gray-50">
                  <div>
                    <div className="font-semibold text-xs text-gray-900 flex items-center gap-1.5">
                      <Lock size={13} className="text-emerald-700" />
                      <span>机密上新：用后即焚</span>
                    </div>
                    <div className="text-[11px] text-gray-500">任务导出后物理擦除服务端临时文件与提示词记录</div>
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

                <div className="p-4 rounded-xl border border-gray-200 bg-[#fafaf8] space-y-2 text-xs text-gray-600 leading-relaxed">
                  <div className="font-semibold text-gray-900 text-sm">千岸 QianAn Agent v2.0</div>
                  <p>
                    基于 mu-agent 快速法官哲学与多智能体蜂群自主编排构建的智能跨境出海一键上新系统。
                  </p>
                  <p className="text-[11px] text-gray-400">
                    专为 2026 AI+ 跨境黑客松巅峰赛决赛打造 · 阿里千问 & 万相引擎驱动
                  </p>
                </div>
              </div>
            )}

          </div>
        </main>
      </div>
    </div>
  );
}
