"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowUp, Bot, Check, ChevronRight, FileArchive, FolderOpen, Globe2,
  ImagePlus, KeyRound, Layers, Menu, MessageSquarePlus, Package, PanelRight,
  Settings2, ShieldCheck, Sparkles, Square, Trash2, X,
} from "lucide-react";
import { useChat } from "@/hooks/useChat";
import { ChatMessages } from "@/components/chat/ChatMessages";
import { Enter, Feedback, PressButton, Reveal } from "@/components/MotionUI";
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
  const fileRef = useRef<HTMLInputElement>(null);

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
    setSettingsOpen(false);
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
              onClick={() => setSettingsOpen((value) => !value)}
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
      <Reveal open={settingsOpen} id="chat-platform-settings">
        <div className="agent-chat-platform-settings">
          <div><strong>目标平台</strong><span>Agent 会分别适配语言、规则和素材</span></div>
          <div className="agent-chat-platform-list">
            {PLATFORM_META.map((platform) => {
              const selected = platforms.includes(platform.key);
              return (
                <PressButton
                  key={platform.key}
                  aria-pressed={selected}
                  onClick={() => setPlatforms((current) => selected ? current.filter((key) => key !== platform.key) : [...current, platform.key])}
                >
                  {platform.name}{selected && <Check size={13} />}
                </PressButton>
              );
            })}
          </div>

          <div style={{ marginTop: 18, paddingTop: 16, borderTop: "1px solid rgba(0,0,0,0.08)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 6 }}>
              <KeyRound size={14} />
              <strong style={{ fontSize: 13 }}>使用自己的 API Key（可选）</strong>
            </div>
            <p style={{ fontSize: 12, lineHeight: 1.6, opacity: 0.7, margin: "0 0 10px" }}>
              服务端额度够用时无需填写。填了之后，本次浏览器里的生成会走你自己的阿里云百炼额度，
              Key 只存在你本地浏览器，不会上传留存。
            </p>
            <input
              type="password"
              value={byokKey}
              onChange={(e) => setByokKey(e.target.value)}
              placeholder="百炼 API Key（sk-…，用于文案与商品理解）"
              style={{
                width: "100%", padding: "9px 11px", fontSize: 12.5, borderRadius: 8,
                border: "1px solid rgba(0,0,0,0.14)", background: "rgba(255,255,255,0.9)",
                marginBottom: 8, outline: "none",
              }}
            />
            <input
              type="password"
              value={byokImgKey}
              onChange={(e) => setByokImgKey(e.target.value)}
              placeholder="万相出图 Key（可选，留空则复用上面的 Key）"
              style={{
                width: "100%", padding: "9px 11px", fontSize: 12.5, borderRadius: 8,
                border: "1px solid rgba(0,0,0,0.14)", background: "rgba(255,255,255,0.9)",
                marginBottom: 10, outline: "none",
              }}
            />
            <div style={{ display: "flex", gap: 8 }}>
              <PressButton onClick={saveByok} style={{ fontSize: 12.5, padding: "7px 14px", borderRadius: 8, background: "#1F201D", color: "#fff" }}>
                保存
              </PressButton>
              {(byokKey || byokImgKey) && (
                <PressButton
                  onClick={() => {
                    setByokKey("");
                    setByokImgKey("");
                    localStorage.removeItem(BYOK_STORAGE_KEY);
                    localStorage.removeItem("qianan_byok_dashscope_key");
                    setSettingsOpen(false);
                  }}
                  style={{ fontSize: 12.5, padding: "7px 14px", borderRadius: 8, border: "1px solid rgba(0,0,0,0.14)" }}
                >
                  清除
                </PressButton>
              )}
            </div>
          </div>
        </div>
      </Reveal>
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
          <Link href="/workbench"><Layers size={16} />任务工作台</Link>
          <Link href="/files"><FolderOpen size={16} />文件管理</Link>
          <Link href="/rules"><ShieldCheck size={16} />平台规则</Link>
          <Link href="/login"><Package size={16} />账户与登录</Link>
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
            <Link href="/workbench">全部任务 <ChevronRight size={14} /></Link>
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
              {QUICK_STARTS.map((prompt) => <PressButton key={prompt} onClick={() => setInput(prompt)}>{prompt}<ArrowUp size={13} /></PressButton>)}
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
          <header><div><FileArchive size={17} /><strong>实时产物</strong></div><PressButton aria-label="关闭产物" onClick={() => setOutputOpen(false)}><X size={17} /></PressButton></header>
          <div className="agent-chat-progress"><span style={{ width: `${Math.max(4, Math.round((snapshot.progress || 0) * 100))}%` }} /></div>
          <div className="agent-chat-output-state"><span>{snapshot.status === "done" ? "已完成" : "Agent 正在工作"}</span><small>{snapshot.stage || "规划任务"}</small></div>
          <div className="agent-chat-listings">
            {snapshot.listings.length === 0 ? (
              <div className="agent-chat-output-wait"><Bot size={25} /><p>产物会随着 Agent 执行实时出现</p></div>
            ) : snapshot.listings.map((listing) => (
              <article key={listing.platform}>
                <header><span>{listing.display_name || listing.platform}</span><small className={listing.compliance_passed ? "is-pass" : "is-warn"}>{listing.compliance_passed ? "合规通过" : "需要检查"}</small></header>
                <h2>{listing.title || "正在生成标题…"}</h2>
                {listing.bullets.slice(0, 3).map((bullet) => <p key={bullet}>• {bullet}</p>)}
                {(listing.images?.[0] || listing.detail_images?.[0]) && <img src={listing.images?.[0] || listing.detail_images?.[0]} alt={`${listing.display_name || listing.platform} 产物`} />}
              </article>
            ))}
          </div>
        </aside>
      )}
    </main>
  );
}
