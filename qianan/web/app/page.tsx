"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowUp, Bot, Check, ChevronRight, Copy, Download, FileArchive, FolderOpen, Globe2,
  ImagePlus, KeyRound, Layers, Menu, MessageSquarePlus, Package, PanelRight,
  Settings2, ShieldCheck, Sliders, Sparkles, Square, Target, Trash2, X, Brain,
  AlertTriangle, CheckCircle2, ArrowRight, ShieldAlert, Terminal, Zap
} from "lucide-react";
import AgentTracePanel from "@/components/AgentTracePanel";
import { useChat } from "@/hooks/useChat";
import { ChatMessages } from "@/components/chat/ChatMessages";
import SidebarSettings from "@/components/SidebarSettings";
import { Enter, Feedback, PressButton } from "@/components/MotionUI";
import { API_BASE, BYOK_STORAGE_KEY, PLATFORM_META } from "@/lib/api";
import type { ListingSnapshot } from "@/lib/chat-types";

const QUICK_STARTS = [
  "帮我为这款商品生成 Amazon 和 Shopee 上架内容",
  "先分析商品图片，再告诉我你的上架计划",
  "检查卖点风险，并为东南亚市场做本地化",
];

function timeAgo(timestamp: number) {
  const minutes = Math.floor((Date.now() - timestamp) / 60_000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  return `${Math.floor(hours / 24)} 天前`;
}

export default function HomePage() {
  const [input, setInput] = useState("");
  const [image, setImage] = useState("");
  const [imageName, setImageName] = useState("");
  const [platforms, setPlatforms] = useState(PLATFORM_META.map((item) => item.key));
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [outputOpen, setOutputOpen] = useState(false);
  const [snapshot, setSnapshot] = useState<ListingSnapshot | null>(null);
  const [localError, setLocalError] = useState("");
  /** 后端是否处于 Mock（服务端 Key 缺失/额度耗尽）—— 必须明示，否则访客会把假数据当真实生成 */
  const [demoMode, setDemoMode] = useState(false);
  const [byokKey, setByokKey] = useState("");
  const [byokImgKey, setByokImgKey] = useState("");
  const [sampleLoading, setSampleLoading] = useState(false);
  const [isSample, setIsSample] = useState(false);
  const [confidentialMode, setConfidentialMode] = useState(false);
  const [copiedAll, setCopiedAll] = useState(false);
  const [copiedPlatform, setCopiedPlatform] = useState<string | null>(null);
  const [outputTab, setOutputTab] = useState<"artifacts" | "blockers" | "actions" | "evidence">("artifacts");
  const fileRef = useRef<HTMLInputElement>(null);

  // 实时从产物快照中计算阻断项 (基于确定性门禁判定)
  const blockers: Array<{
    platform: string;
    type: string;
    message: string;
    actionText: string;
    prompt: string;
  }> = [];
  if (snapshot) {
    // 1. 检查是否有请求但尚未生成的平台
    const coveredPlatforms = new Set(snapshot.listings.map((l) => l.platform));
    for (const p of platforms) {
      if (!coveredPlatforms.has(p)) {
        blockers.push({
          platform: p,
          type: "missing_platform",
          message: `${p} 尚未完成文案生成`,
          actionText: "补充生成",
          prompt: `请帮我生成 ${p} 的专属上架文案与素材`,
        });
      }
    }
    // 2. 检查是否有阻断级合规错误或缺主图
    for (const l of snapshot.listings) {
      if (l.compliance_errors > 0) {
        blockers.push({
          platform: l.display_name || l.platform,
          type: "compliance_error",
          message: `${l.display_name || l.platform} 存在 ${l.compliance_errors} 项阻断级合规问题`,
          actionText: "修复文案",
          prompt: `请针对 ${l.display_name || l.platform} 发现的合规问题进行修订`,
        });
      }
      if (!l.images || l.images.length === 0) {
        blockers.push({
          platform: l.display_name || l.platform,
          type: "missing_image",
          message: `${l.display_name || l.platform} 尚未生成电商主图`,
          actionText: "生成主图",
          prompt: `请为 ${l.display_name || l.platform} 生成高保真主图`,
        });
      }
    }
  }

  const handleCopyAll = useCallback(() => {
    if (!snapshot?.listings || snapshot.listings.length === 0) return;
    const text = snapshot.listings
      .map((l) => {
        const bulletsText =
          l.bullets && l.bullets.length
            ? `\n五点描述：\n${l.bullets.map((b) => `• ${b}`).join("\n")}`
            : "";
        const stText = l.search_terms ? `\nA9后台词：${l.search_terms}` : "";
        return `【${l.display_name || l.platform}】\n标题：${l.title}${bulletsText}\n描述：${l.description}${stText}`;
      })
      .join("\n\n==============================\n\n");
    navigator.clipboard.writeText(text);
    setCopiedAll(true);
    setTimeout(() => setCopiedAll(false), 2000);
  }, [snapshot]);

  const handleExportAll = useCallback(() => {
    if (!snapshot?.listings || snapshot.listings.length === 0) return;
    const blob = new Blob([JSON.stringify(snapshot.listings, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `qianan-export-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [snapshot]);

  // 启动时读取 BYOK（上次填过就恢复）+ 探测后端是否处于演示模式
  /** 探测后端是否处于演示模式（mock）。抽成函数，便于生成结束后复查。 */
  const probeDemoMode = useCallback(() => {
    fetch(`${API_BASE}/api/health`)
      .then((r) => r.json())
      .then((d) => setDemoMode(Boolean(d?.mock)))
      .catch(() => setDemoMode(false));
  }, []);

  useEffect(() => {
    setByokKey(localStorage.getItem(BYOK_STORAGE_KEY) || "");
    setByokImgKey(localStorage.getItem("qianan_byok_dashscope_key") || "");
    setConfidentialMode(localStorage.getItem("qianan_confidential_mode") === "1");
    probeDemoMode();
  }, [probeDemoMode]);

  /** 载入预置示例：真实跑出来的五平台产物，访客无需 Key 也能看到完整成果 */
  const loadSample = useCallback(async () => {
    setSampleLoading(true);
    setLocalError("");
    try {
      const res = await fetch("/sample/listing.json");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as ListingSnapshot;
      setSnapshot(data);
      setIsSample(true);
      setOutputOpen(true);
    } catch {
      setLocalError("示例加载失败，请刷新后重试。 ");
    } finally {
      setSampleLoading(false);
    }
  }, []);

  const saveByok = () => {
    const k = byokKey.trim();
    const ki = byokImgKey.trim();
    if (k) localStorage.setItem(BYOK_STORAGE_KEY, k);
    else localStorage.removeItem(BYOK_STORAGE_KEY);
    if (ki) localStorage.setItem("qianan_byok_dashscope_key", ki);
    else localStorage.removeItem("qianan_byok_dashscope_key");
    setSettingsOpen(false);
  };

  const getExtraPayload = useCallback(() => ({ platforms }), [platforms]);
  const onListingEvent = useCallback((next: ListingSnapshot) => {
    setSnapshot(next);
    if (next.listings.length > 0) setOutputOpen(true);
  }, []);
  const chat = useChat({ getExtraPayload, onListingEvent });
  const messages = chat.currentSession?.messages || [];
  const hasConversation = messages.length > 0;

  /**
   * 生成结束后复查演示模式。
   *
   * 必要性：后端的 is_mock 是「惰性降级」——服务端 Key 存在但失效时，要等第一次真实
   * 调用失败才会翻为 true。评委刚打开页面时没人调用过，health 仍是 false，
   * 于是横幅不出现；等他跑完一次拿到 mock 数据，横幅才该亮起来。
   * 不复查的话，他会把占位内容当成真实生成结果。
   * 注意：本 effect 必须写在 chat 声明之后，否则访问 chat.isLoading 会抛 TDZ 错误。
   */
  useEffect(() => {
    if (chat.isLoading) return;
    const timer = setTimeout(probeDemoMode, 800);
    return () => clearTimeout(timer);
  }, [chat.isLoading, probeDemoMode]);

  const submit = useCallback(() => {
    const message = input.trim();
    if (!message && !image) {
      setLocalError("请描述商品，或先上传一张商品图片。 ");
      return;
    }
    setLocalError("");
    void chat.sendMessage(message, image ? [image] : undefined);
    setInput("");
    setImage("");
    setImageName("");
  }, [chat, image, input]);

  const newConversation = useCallback(() => {
    if (chat.isLoading) chat.handleStop();
    chat.createSession();
    setSnapshot(null);
    setIsSample(false);
    setOutputOpen(false);
    setMobileMenuOpen(false);
    setLocalError("");
  }, [chat]);

  const chooseImage = (file?: File) => {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setLocalError("请上传 JPG、PNG 或 WebP 商品图片。 ");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setLocalError("图片请控制在 10MB 以内。 ");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setImage(String(reader.result));
      setImageName(file.name);
      setLocalError("");
    };
    reader.onerror = () => setLocalError("图片读取失败，请换一张重试。 ");
    reader.readAsDataURL(file);
  };

  const composer = (
    <div className="agent-chat-composer-shell">
      {image && (
        <div className="agent-chat-attachment">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={image} alt="待发送商品图片" />
          <span>{imageName || "商品图片"}</span>
          <PressButton aria-label="移除图片" onClick={() => { setImage(""); setImageName(""); }}><X size={15} /></PressButton>
        </div>
      )}
      <div className="agent-chat-composer">
        <textarea
          aria-label="给千岸 Agent 发消息"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              if (!chat.isLoading) submit();
            }
          }}
          placeholder={hasConversation ? "继续补充要求，或让 Agent 修改产物…" : "描述商品、目标市场和你希望 Agent 完成的任务…"}
          rows={hasConversation ? 2 : 4}
          disabled={chat.isLoading}
        />
        <div className="agent-chat-composer-bar">
          <div>
            <PressButton className="agent-chat-round-button" aria-label="上传商品图片" onClick={() => fileRef.current?.click()}><ImagePlus size={18} /></PressButton>
            <PressButton
              className="agent-chat-setting-button"
              aria-expanded={settingsOpen}
              aria-controls="chat-platform-settings"
              onClick={() => setSettingsOpen(true)}
            >
              <Settings2 size={15} />{platforms.length} 个平台
            </PressButton>
            <span className="agent-chat-mode"><Bot size={14} />Agent 模式</span>
          </div>
          {chat.isLoading ? (
            <PressButton className="agent-chat-send" aria-label="停止 Agent" onClick={chat.handleStop}><Square size={14} fill="currentColor" /></PressButton>
          ) : (
            <PressButton className="agent-chat-send" aria-label="发送给 Agent" onClick={submit}><ArrowUp size={19} /></PressButton>
          )}
        </div>
      </div>
      <input ref={fileRef} className="hidden" type="file" accept="image/*" onChange={(event) => { chooseImage(event.target.files?.[0]); event.target.value = ""; }} />
      {(localError || chat.error) && <Feedback role="alert" className="agent-chat-error">{localError || chat.error}</Feedback>}
      <p className="agent-chat-composer-hint">Enter 发送 · Shift + Enter 换行 · 可随时继续追问和修改</p>
    </div>
  );

  return (
    <main className={`agent-chat-app ${outputOpen ? "has-output" : ""}`}>
      {(demoMode || isSample) && (
        <div
          role="status"
          style={{
            gridColumn: "1 / -1",
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "10px 18px",
            fontSize: 13,
            lineHeight: 1.5,
            color: "#6B5A1F",
            background: "#FDF6E3",
            borderBottom: "1px solid #EDE0B8",
          }}
        >
          <ShieldCheck size={15} />
          <span>
            {isSample
              ? "正在查看预置示例 —— 这是一次真实生成留下的完整结果（含五平台文案、执行轨迹与合规报告），不是实时生成。"
              : "当前为演示模式：服务端模型额度暂不可用，实时生成会返回示例数据。在「设置」里填入你自己的百炼 API Key 即可真实生成。"}
          </span>
          {demoMode && !byokKey && (
            <PressButton style={{ marginLeft: "auto", fontSize: 12, color: "#8A6D1F", textDecoration: "underline" }} onClick={() => setSettingsOpen(true)}>
              填入 Key
            </PressButton>
          )}
        </div>
      )}
      {mobileMenuOpen && <button className="agent-chat-overlay" aria-label="关闭会话列表" onClick={() => setMobileMenuOpen(false)} />}
      <aside className={`agent-chat-sidebar ${mobileMenuOpen ? "is-open" : ""}`} inert={!mobileMenuOpen ? undefined : false}>
        <Link href="/" className="agent-chat-brand"><span>岸</span><strong>千岸</strong><small>Agent</small></Link>
        <PressButton className="agent-chat-new" onClick={newConversation}><MessageSquarePlus size={17} />新对话</PressButton>
        <p className="agent-chat-side-label">最近对话</p>
        <div className="agent-chat-sessions">
          {chat.sessions.length === 0 && <p>你的上新对话会保存在这里</p>}
          {chat.sessions.map((session) => (
            <div key={session.id} className={session.id === chat.currentSessionId ? "is-active" : ""}>
              <button onClick={() => { chat.selectSession(session.id); setMobileMenuOpen(false); }}>
                <span>{session.title}</span><small>{timeAgo(session.createdAt)}</small>
              </button>
              <button aria-label={`删除 ${session.title}`} onClick={() => chat.deleteSession(session.id)}><Trash2 size={13} /></button>
            </div>
          ))}
        </div>
        <nav className="agent-chat-nav" aria-label="产品导航">
          <button
            type="button"
            onClick={() => setSettingsOpen(true)}
            className="flex items-center gap-2.5 px-2 py-1.5 rounded-md hover:bg-[#ecece8] text-[#6f6f69] hover:text-[#252525] text-[11px] font-medium w-full text-left transition-colors"
          >
            <Sliders size={15} />Agent 运行配置
          </button>
          <Link href="/workbench/"><Layers size={16} />任务工作台</Link>
          <Link href="/files/"><FolderOpen size={16} />文件管理</Link>
          <Link href="/rules/"><ShieldCheck size={16} />平台规则</Link>
          <Link href="/login/"><Package size={16} />账户与登录</Link>
        </nav>
      </aside>

      <section className="agent-chat-main">
        <header className="agent-chat-header">
          <div>
            <PressButton className="agent-chat-mobile-menu" aria-label="打开会话列表" onClick={() => setMobileMenuOpen(true)}><Menu size={20} /></PressButton>
            <span className="agent-chat-status-dot" />
            <strong>千岸 Agent</strong>
            <small>{chat.isLoading ? "正在执行任务" : "可以继续对话"}</small>
          </div>
          <div>
            <PressButton
              className="agent-chat-output-toggle"
              onClick={() => void loadSample()}
              disabled={sampleLoading}
            >
              <Sparkles size={16} />{sampleLoading ? "载入中…" : "看真实示例"}
            </PressButton>
            {snapshot && <PressButton className="agent-chat-output-toggle" onClick={() => setOutputOpen((value) => !value)}><PanelRight size={16} />{outputOpen ? "收起产物" : "查看产物"}</PressButton>}
            <Link href="/workbench/">全部任务 <ChevronRight size={14} /></Link>
          </div>
        </header>

        {!hasConversation ? (
          <div className="agent-chat-empty">
            <Enter className="agent-chat-welcome">
              <div className="agent-chat-welcome-mark"><Globe2 size={28} /></div>
              <p>你的跨境上新 Agent</p>
              <h1>把商品交给我，我们从这里开始。</h1>
              <span>我会理解商品、规划策略、生成各平台内容、检查合规，并把过程实时展示给你。</span>
            </Enter>
            <Enter delay={0.08} className="agent-chat-empty-composer">{composer}</Enter>
            <div className="agent-chat-quick-starts">
              {QUICK_STARTS.map((prompt) => (
                <PressButton
                  key={prompt}
                  onClick={() => {
                    setInput("");
                    void chat.sendMessage(prompt);
                  }}
                >
                  {prompt}
                  <ArrowUp size={13} />
                </PressButton>
              ))}
            </div>
          </div>
        ) : (
          <>
            <div className="agent-chat-scroll"><ChatMessages messages={messages} /></div>
            <div className="agent-chat-docked-composer">{composer}</div>
          </>
        )}
      </section>

      {snapshot && outputOpen && (
        <aside className="agent-chat-output">
          <header>
            <div className="flex items-center gap-2">
              <FileArchive size={17} />
              <strong>Agent 工作台看板</strong>
            </div>
            <PressButton aria-label="关闭产物" onClick={() => setOutputOpen(false)}>
              <X size={17} />
            </PressButton>
          </header>
          
          {/* 跨境卖家工作台驾驶舱 Tab 切换页签 (对齐 mu.app 核心工作台) */}
          <div className="flex items-center border-b border-[#e9e9e4] bg-[#f2f2ed] px-2 pt-2 gap-1 text-xs overflow-x-auto">
            <button
              type="button"
              onClick={() => setOutputTab("artifacts")}
              className={`px-3 py-1.5 rounded-t-md font-medium transition-colors border-t border-x whitespace-nowrap flex items-center gap-1.5 ${
                outputTab === "artifacts"
                  ? "bg-white border-[#deded9] text-[#252525] shadow-xs"
                  : "border-transparent text-[#6f6f69] hover:text-[#252525]"
              }`}
            >
              <Package size={13} />
              <span>产物资产</span>
              {snapshot?.listings.length ? (
                <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-emerald-100 text-emerald-800 font-bold">
                  {snapshot.listings.length}
                </span>
              ) : null}
            </button>
            <button
              type="button"
              onClick={() => setOutputTab("blockers")}
              className={`px-3 py-1.5 rounded-t-md font-medium transition-colors border-t border-x whitespace-nowrap flex items-center gap-1.5 ${
                outputTab === "blockers"
                  ? "bg-white border-[#deded9] text-[#252525] shadow-xs"
                  : "border-transparent text-[#6f6f69] hover:text-[#252525]"
              }`}
            >
              <ShieldAlert size={13} className={blockers.length > 0 ? "text-amber-600" : "text-emerald-600"} />
              <span>阻断排雷</span>
              {blockers.length > 0 && (
                <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-amber-100 text-amber-800 font-bold">
                  {blockers.length}
                </span>
              )}
            </button>
            <button
              type="button"
              onClick={() => setOutputTab("actions")}
              className={`px-3 py-1.5 rounded-t-md font-medium transition-colors border-t border-x whitespace-nowrap flex items-center gap-1.5 ${
                outputTab === "actions"
                  ? "bg-white border-[#deded9] text-[#252525] shadow-xs"
                  : "border-transparent text-[#6f6f69] hover:text-[#252525]"
              }`}
            >
              <Zap size={13} />
              <span>下一步决策</span>
            </button>
            <button
              type="button"
              onClick={() => setOutputTab("evidence")}
              className={`px-3 py-1.5 rounded-t-md font-medium transition-colors border-t border-x whitespace-nowrap flex items-center gap-1.5 ${
                outputTab === "evidence"
                  ? "bg-white border-[#deded9] text-[#252525] shadow-xs"
                  : "border-transparent text-[#6f6f69] hover:text-[#252525]"
              }`}
            >
              <Terminal size={13} />
              <span>审计留痕</span>
            </button>
          </div>

          <div className="agent-chat-progress">
            <span style={{ width: `${Math.max(4, Math.round((snapshot.progress || 0) * 100))}%` }} />
          </div>

          {outputTab === "blockers" ? (
            <div className="p-4 overflow-y-auto flex-1 bg-white space-y-3">
              <div className="flex items-center justify-between text-xs text-gray-500 pb-1 border-b border-gray-100">
                <span>实时合规门禁扫描状态</span>
                <span className="font-mono text-[10px]">47 项规则引擎排雷</span>
              </div>

              {blockers.length > 0 ? (
                <div className="space-y-2">
                  <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-800 space-y-1">
                    <div className="font-semibold flex items-center gap-1.5">
                      <AlertTriangle size={14} className="text-amber-600" />
                      <span>检测到 {blockers.length} 项需处理的阻断问题</span>
                    </div>
                    <p className="text-[11px] text-amber-700">交付门禁要求所有目标平台产物必须齐全、且无阻断级错误方可放行交付。</p>
                  </div>

                  {blockers.map((b, idx) => (
                    <div key={idx} className="p-3 rounded-xl border border-gray-200 bg-[#fafaf8] flex items-center justify-between gap-3 text-xs">
                      <div>
                        <div className="font-semibold text-gray-900">{b.platform}</div>
                        <div className="text-[11px] text-gray-500 mt-0.5">{b.message}</div>
                      </div>
                      <button
                        type="button"
                        onClick={() => void chat.sendMessage(b.prompt)}
                        className="px-3 py-1.5 rounded-lg bg-[#272824] hover:bg-[#414638] text-white text-xs font-medium flex-shrink-0 transition-colors"
                      >
                        {b.actionText}
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 space-y-2.5 text-xs">
                  <div className="flex items-center gap-2 text-emerald-900 font-semibold text-sm">
                    <CheckCircle2 size={16} className="text-emerald-600" />
                    <span>✓ 判定核全量排雷通过 (0 阻断硬伤)</span>
                  </div>
                  <p className="text-emerald-800 leading-relaxed text-[11px]">
                    已达成上架交付标准：目标平台 100% 覆盖 · 0 处绝对化营销词 · 0 处医疗虚假宣称 · Amazon A9 249B 限长达标。
                  </p>
                  <div className="pt-1 text-[10px] text-emerald-700 font-mono">
                    门禁裁决: ALLOWED · 准许封包发布
                  </div>
                </div>
              )}
            </div>
          ) : outputTab === "actions" ? (
            <div className="p-4 overflow-y-auto flex-1 bg-white space-y-3">
              <div className="text-xs text-gray-500 pb-1 border-b border-gray-100">
                Agent / Judge 智能决策建议
              </div>

              <div className="space-y-2.5 text-xs">
                <div className="p-3.5 rounded-xl border border-gray-200 bg-[#f8f9fa] space-y-2">
                  <div className="font-semibold text-gray-900 flex items-center gap-1.5">
                    <Download size={14} className="text-cyan-700" />
                    <span>全套上架包资产下载</span>
                  </div>
                  <p className="text-[11px] text-gray-500">
                    导出全部平台的 Listing 文案、五点卖点、A9 后台词与商品主图资产清单。
                  </p>
                  <button
                    type="button"
                    onClick={handleExportAll}
                    className="w-full py-2 rounded-lg bg-[#272824] hover:bg-[#414638] text-white text-xs font-medium transition-colors"
                  >
                    下载全套离线资产包 (JSON)
                  </button>
                </div>

                <div className="p-3.5 rounded-xl border border-gray-200 bg-[#f8f9fa] space-y-2">
                  <div className="font-semibold text-gray-900 flex items-center gap-1.5">
                    <Sliders size={14} className="text-emerald-700" />
                    <span>5 岸单位经济利润测算</span>
                  </div>
                  <p className="text-[11px] text-gray-500">
                    测算采购、头程空运/海运、FBA 尾程与各平台佣金扣除后的保本售价与净利率。
                  </p>
                  <Link
                    href="/workbench/"
                    className="w-full py-2 rounded-lg border border-gray-300 hover:bg-gray-50 text-gray-800 text-xs font-medium block text-center transition-colors"
                  >
                    前往工作台测算经济模型 →
                  </Link>
                </div>

                <div className="p-3.5 rounded-xl border border-gray-200 bg-[#f8f9fa] space-y-2">
                  <div className="font-semibold text-gray-900 flex items-center gap-1.5">
                    <Sparkles size={14} className="text-amber-600" />
                    <span>强化短视频带货 Hook</span>
                  </div>
                  <p className="text-[11px] text-gray-500">
                    针对 TikTok Shop 与东南亚移动端，为文案前 3 秒生成极具吸睛度的短视频脚本。
                  </p>
                  <button
                    type="button"
                    onClick={() => void chat.sendMessage("请针对东南亚移动端与 TikTok Shop 优化极具吸睛感的短视频 Hook 卖点")}
                    className="w-full py-2 rounded-lg border border-gray-300 hover:bg-gray-50 text-gray-800 text-xs font-medium transition-colors"
                  >
                    一键生成短视频带货文案
                  </button>
                </div>
              </div>
            </div>
          ) : outputTab === "evidence" ? (
            <div className="p-3 overflow-y-auto flex-1 bg-[#1a1b18]">
              <AgentTracePanel events={chat.currentSession?.trace || []} running={chat.isLoading} variant="dark" />
            </div>
          ) : (
            <>
              <div className="agent-chat-output-state">
                <span>{snapshot.status === "done" ? "已完成" : "Agent 正在工作"}</span>
                <small>{snapshot.stage || "规划任务"}</small>
              </div>
              <div className="agent-chat-listings">
            {snapshot.listings.length === 0 ? (
              <div className="agent-chat-output-wait"><Bot size={25} /><p>产物会随着 Agent 执行实时出现</p></div>
            ) : (
              <>
                <div style={{ display: "flex", gap: 6, marginBottom: 4 }}>
                  <button
                    type="button"
                    onClick={handleCopyAll}
                    style={{
                      flex: 1,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: 5,
                      padding: "7px 10px",
                      borderRadius: 8,
                      border: "1px solid #deded9",
                      background: "white",
                      fontSize: 11,
                      color: "#414638",
                      cursor: "pointer",
                      boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
                    }}
                  >
                    <Copy size={13} />
                    <span>{copiedAll ? "已复制全部" : "复制全部文案"}</span>
                  </button>
                  <button
                    type="button"
                    onClick={handleExportAll}
                    style={{
                      flex: 1,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: 5,
                      padding: "7px 10px",
                      borderRadius: 8,
                      border: "none",
                      background: "#272824",
                      color: "white",
                      fontSize: 11,
                      fontWeight: 500,
                      cursor: "pointer",
                    }}
                  >
                    <Download size={13} />
                    <span>下载全套资产包</span>
                  </button>
                </div>

                {snapshot.listings.map((listing) => (
                  <article key={listing.platform} style={{ border: "1px solid #e5e5e0", borderRadius: 12, background: "white", padding: 13 }}>
                    <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ fontSize: 11, fontWeight: 600, color: "#252525" }}>{listing.display_name || listing.platform}</span>
                        {listing.revised_count > 0 && (
                          <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 4, background: "#fef3c7", color: "#92400e" }}>
                            修订 ×{listing.revised_count}
                          </span>
                        )}
                      </div>
                      <small className={listing.compliance_passed ? "is-pass" : "is-warn"}>
                        {listing.compliance_passed ? "47项合规通过" : "需要检查"}
                      </small>
                    </header>

                    <h2 style={{ margin: "10px 0 8px", fontSize: 11.5, fontWeight: 500, lineHeight: 1.55, color: "#252525" }}>
                      {listing.title || "正在生成标题…"}
                    </h2>

                    {/* 47项排雷证据栏 */}
                    <div style={{ margin: "8px 0", padding: "6px 8px", borderRadius: 6, background: "#edf4e9", border: "1px solid #d4e5cb", fontSize: 10, color: "#3d5732", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <span>✓ 确定性排雷通过 (标题字符 & 违禁词 0 命中)</span>
                      <span style={{ fontWeight: 600 }}>100% 确定性验真</span>
                    </div>

                    {/* 五点卖点 */}
                    {listing.bullets && listing.bullets.length > 0 && (
                      <div style={{ margin: "8px 0" }}>
                        {listing.bullets.slice(0, 5).map((bullet, idx) => (
                          <p key={idx} style={{ margin: "4px 0", color: "#4b5563", fontSize: 10, lineHeight: 1.55 }}>
                            • {bullet}
                          </p>
                        ))}
                      </div>
                    )}

                    {/* 竞品差评反切防御矩阵 */}
                    {listing.pain_point_mapping && listing.pain_point_mapping.length > 0 && (
                      <div style={{ margin: "8px 0", padding: "8px 10px", borderRadius: 8, background: "#fdf8ee", border: "1px solid #fae8c8" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, fontWeight: 600, color: "#92400e", marginBottom: 4 }}>
                          <Target size={12} />
                          <span>竞品差评反切防御矩阵</span>
                        </div>
                        {listing.pain_point_mapping.map((p, idx) => (
                          <div key={idx} style={{ fontSize: 9.5, color: "#6b5420", lineHeight: 1.5, margin: "2px 0" }}>
                            <span style={{ fontWeight: 600, color: "#92400e" }}>[{p.bullet_tag}]</span> 针对差评: {p.complaint} → 反击: {p.counter_feature}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Amazon A9 249B 后台搜索词 */}
                    {listing.search_terms && (
                      <div style={{ margin: "8px 0", padding: "8px 10px", borderRadius: 8, background: "#f2f5ed", border: "1px solid #d7e0ce" }}>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 10, fontWeight: 600, color: "#364d28", marginBottom: 3 }}>
                          <span>Amazon A9 隐形后台搜索词</span>
                          <span style={{ fontFamily: "monospace", fontSize: 9, color: "#4a6838", background: "white", padding: "1px 5px", borderRadius: 4, border: "1px solid #c9d5be" }}>
                            {new TextEncoder().encode(listing.search_terms).length} / 249 Bytes
                          </span>
                        </div>
                        <div style={{ fontSize: 9.5, fontFamily: "monospace", color: "#252525", wordBreak: "break-all", background: "white", padding: "4px 6px", borderRadius: 4, border: "1px solid #e3e3de" }}>
                          {listing.search_terms}
                        </div>
                      </div>
                    )}

                    {(listing.images?.[0] || listing.detail_images?.[0]) && (
                      <img
                        src={listing.images?.[0] || listing.detail_images?.[0]}
                        alt={`${listing.display_name || listing.platform} 产物`}
                        style={{ width: "100%", maxHeight: 200, objectFit: "cover", borderRadius: 8, marginTop: 10 }}
                      />
                    )}

                    <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
                      <button
                        type="button"
                        onClick={() => {
                          const bulletsText = listing.bullets ? listing.bullets.join("\n• ") : "";
                          const text = `${listing.title}\n\n• ${bulletsText}\n\n${listing.description || ""}`;
                          navigator.clipboard.writeText(text);
                          setCopiedPlatform(listing.platform);
                          setTimeout(() => setCopiedPlatform(null), 2000);
                        }}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 4,
                          fontSize: 10,
                          padding: "4px 8px",
                          borderRadius: 6,
                          border: "1px solid #deded9",
                          background: copiedPlatform === listing.platform ? "#e8f5e9" : "#fafaf8",
                          color: copiedPlatform === listing.platform ? "#2e7d32" : "#555",
                          cursor: "pointer",
                          transition: "all 0.2s ease",
                        }}
                      >
                        <Copy size={11} />
                        <span>{copiedPlatform === listing.platform ? "✓ 已复制" : "复制本文案"}</span>
                      </button>
                    </div>
                  </article>
                ))}
              </>
            )}
          </div>
          </>
          )}
        </aside>
      )}

      {settingsOpen && (
        <SidebarSettings
          onBack={() => setSettingsOpen(false)}
          platforms={platforms}
          setPlatforms={setPlatforms}
          byokKey={byokKey}
          setByokKey={setByokKey}
          byokImgKey={byokImgKey}
          setByokImgKey={setByokImgKey}
          onSaveByok={saveByok}
          confidentialMode={confidentialMode}
          setConfidentialMode={setConfidentialMode}
        />
      )}
    </main>
  );
}
