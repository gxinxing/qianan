// 千岸侧边栏逻辑：读表单 → /api/audit 体检；填充示例；跳转完整工作台。
// 与 /copilot 页共用同一套后端与协议，这里是「真浏览器扩展」里的瘦版。
const API_BASE = "http://localhost:8001";

const SAMPLE = {
  title: "Acme Portable Blender 380ml USB-C Rechargeable Juicer Cup for Smoothies",
  brand: "Acme",
  bullet1: "USB-C FAST CHARGE: full charge in 2 hours, blends up to 15 cups per charge",
  bullet2: "10-SECOND BLENDS: 6 titanium blades crush ice and frozen fruit in seconds",
  bullet3: "DETACHABLE EASY CLEAN: cup body separates from the motor base for rinsing",
  bullet4: "TRAVEL READY: 380ml leak-proof cup fits standard car cup holders",
  bullet5: "FOOD-GRADE MATERIAL: BPA-free Tritan cup body, 12-month warranty included",
  description:
    "Key Features: Acme portable blender with USB-C fast charge and 10-second blending power.\nSpecifications: 380ml BPA-free Tritan cup, 6 titanium blades, 2-hour full charge.\nWarranty: 12 months, friendly customer service within 24 hours.",
  price: "23.99",
  quantity: "100",
};

const statusEl = document.getElementById("status");

function show(kind, text) {
  statusEl.className = kind;
  statusEl.textContent = text;
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function sendToTab(type, payload) {
  const tab = await activeTab();
  if (!tab?.id) throw new Error("找不到当前标签页");
  return chrome.tabs.sendMessage(tab.id, { type, payload });
}

document.getElementById("btn-read").addEventListener("click", async () => {
  try {
    const res = await sendToTab("QA_READ");
    const n = Object.values(res.payload || {}).filter(Boolean).length;
    show("info", `已读取表单，共 ${n} 个非空字段。`);
  } catch (e) {
    show("bad", `读取失败：当前页面没有可识别的上架表单（请打开 mock 演示页或卖家后台）。`);
  }
});

document.getElementById("btn-audit").addEventListener("click", async () => {
  try {
    show("info", "读取表单并体检中…");
    const res = await sendToTab("QA_READ");
    const p = res.payload || {};
    const res2 = await fetch(`${API_BASE}/api/audit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        platform: "amazon",
        title: p.title || "",
        bullets: [p.bullet1, p.bullet2, p.bullet3, p.bullet4, p.bullet5].filter(Boolean),
        description: p.description || "",
        images: p.mainImage ? [p.mainImage] : [],
      }),
    });
    if (!res2.ok) throw new Error(`API ${res2.status}`);
    const result = await res2.json();
    if (result.passed) {
      const warns = result.issues.map((i) => `· ${i.message}`).join("\n");
      show("ok", `体检通过，无阻断级错误${warns ? `\n${warns}` : ""}`);
    } else {
      const lines = result.issues.map((i) => `${i.severity === "error" ? "✗" : "·"} [${i.field}] ${i.message}`).join("\n");
      show("bad", `发现必须修复的错误：\n${lines}`);
    }
  } catch (e) {
    show("bad", `体检失败：${String(e.message || e)}`);
  }
});

document.getElementById("btn-sample").addEventListener("click", async () => {
  try {
    const res = await sendToTab("QA_FILL", SAMPLE);
    show("ok", `已把示例商品填入表单（${res.payload?.filled ?? 0} 个字段），可点击「体检当前表单」验证。`);
  } catch (e) {
    show("bad", "填充失败：请先打开 mock 演示页（/copilot 或 localhost:3000/mock-seller-central.html）");
  }
});

document.getElementById("btn-open").addEventListener("click", () => {
  chrome.tabs.create({ url: "http://localhost:3000/copilot" });
});
