// 把 slides.html 的每个 .slide 截成 1920x1080 PNG
const puppeteer = require('/Users/simon/glm-sniper/node_modules/puppeteer');
const fs = require('fs');
const path = require('path');

const SLIDES_DIR = '/Users/simon/Documents/01_AI and Code Development/AI+跨境黑客松巅峰赛/assets/slides';
const HTML = 'file://' + path.join(SLIDES_DIR, 'slides.html');
const OUT_PREFIX = 'slide';

(async () => {
  const browser = await puppeteer.launch({
    headless: 'new',
    defaultViewport: { width: 1920, height: 1080, deviceScaleFactor: 1 },
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    args: ['--no-sandbox', '--force-device-scale-factor=1']
  });
  const page = await browser.newPage();
  await page.goto(HTML, { waitUntil: 'networkidle0' });
  // 等字体/布局稳定
  await new Promise(r => setTimeout(r, 800));

  const ids = await page.$$eval('.slide[id]', els => els.map(e => e.id));
  console.log('slides:', ids);

  for (let i = 0; i < ids.length; i++) {
    const id = ids[i];
    const num = String(i + 1).padStart(2, '0');
    const out = path.join(SLIDES_DIR, `${OUT_PREFIX}-${num}.png`);

    // 隐藏其他 slide，只显示当前
    await page.evaluate((curId) => {
      document.querySelectorAll('.slide').forEach(s => {
        s.style.display = (s.id === curId) ? 'flex' : 'none';
      });
      document.body.style.background = '#fff';
      document.body.style.margin = '0';
    }, id);

    await new Promise(r => setTimeout(r, 250));

    // 把视口精确设到这个 slide 的 1920x1080
    await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });

    // 截图：只截当前可见 slide 元素，保证刚好 1920x1080
    const el = await page.$('#' + id);
    await el.screenshot({ path: out, type: 'png' });

    // 校验尺寸
    const dim = await page.evaluate(() => {
      const e = document.querySelector('.slide:not([style*="display: none"])') || document.querySelector('.slide');
      const r = e.getBoundingClientRect();
      return { w: Math.round(r.width), h: Math.round(r.height) };
    });
    console.log(`${num} -> ${out}  slide=${dim.w}x${dim.h}`);
  }

  await browser.close();
  console.log('DONE');
})().catch(e => { console.error(e); process.exit(1); });
