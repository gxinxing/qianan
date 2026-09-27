// CloudBase 静态托管导出构建：output:"export" 模式不允许 route handlers（app/api），
// 构建前临时移出、构建后恢复 —— Vercel 构建（VERCEL=1，非 export 模式）不走本脚本。
import { execSync } from "node:child_process";
import { existsSync, renameSync, mkdirSync } from "node:fs";

const API_DIR = "app/imgproxy";
const STASH = ".api-stash-build";

if (!process.env.VERCEL) {
  if (existsSync(API_DIR)) {
    if (!existsSync(STASH)) mkdirSync(STASH);
    renameSync(API_DIR, `${STASH}/api`);
    console.log("[build-export] moved app/api out (route handlers unsupported in export mode)");
  }
}

try {
  execSync("npx next build", { stdio: "inherit" });
} finally {
  if (!process.env.VERCEL && existsSync(`${STASH}/api`)) {
    renameSync(`${STASH}/api`, API_DIR);
    console.log("[build-export] restored app/api");
  }
}
