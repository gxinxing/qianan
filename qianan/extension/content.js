// 千岸侧边栏的内容脚本：与页面约定 data-sc-field 协议（与 mock-seller-central.html 相同）。
// 只读表单 / 按确认回填；不碰任何提交按钮 —— 写操作的安全门在侧边栏人工确认。
(() => {
  const FILL_MAP = {
    title: "title",
    brand: "brand",
    sku: "sku",
    bullet1: "bullet1",
    bullet2: "bullet2",
    bullet3: "bullet3",
    bullet4: "bullet4",
    bullet5: "bullet5",
    description: "description",
    price: "price",
    quantity: "quantity",
  };

  function fields() {
    const out = {};
    document.querySelectorAll("[data-sc-field]").forEach((el) => {
      out[el.getAttribute("data-sc-field")] = el.value;
    });
    const img = document.querySelector("#img-box img, [data-sc-image] img");
    if (img) out.mainImage = img.getAttribute("src");
    return out;
  }

  function fill(payload) {
    let touched = 0;
    Object.keys(FILL_MAP).forEach((key) => {
      const v = payload[key];
      if (v === undefined || v === null) return;
      const el = document.querySelector(`[data-sc-field="${FILL_MAP[key]}"]`);
      if (!el) return;
      el.value = String(v);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      touched++;
    });
    const imgBox = document.querySelector("#img-box, [data-sc-image]");
    if (imgBox && payload.mainImage) {
      imgBox.innerHTML = `<img src="${payload.mainImage}" alt="main image" />`;
      touched++;
    }
    return touched;
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg.type === "QA_READ") {
      sendResponse({ type: "QA_FIELDS", payload: fields() });
    } else if (msg.type === "QA_FILL") {
      const n = fill(msg.payload || {});
      sendResponse({ type: "QA_FILLED", payload: { filled: n } });
    }
    return false;
  });
})();
