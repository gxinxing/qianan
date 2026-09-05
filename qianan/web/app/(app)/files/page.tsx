"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import Nav from "@/components/Nav";
import {
  PackageInfo,
  PLATFORM_META,
  deletePackage,
  fetchFiles,
  fileDownloadUrl,
  zipUrl,
} from "@/lib/api";

function fmtSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function fmtTime(ts: number | null) {
  if (!ts) return "-";
  const d = new Date(ts * 1000);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(
    d.getMinutes()
  ).padStart(2, "0")}`;
}

const KIND_META: Record<string, { label: string; cls: string }> = {
  json: { label: "JSON 导出包", cls: "bg-amber-50 text-amber-600" },
  csv: { label: "后台导入表", cls: "bg-green-50 text-green-700" },
  image: { label: "主图", cls: "bg-brand-50 text-brand-700" },
};

export default function FilesPage() {
  const [packages, setPackages] = useState<PackageInfo[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { packages } = await fetchFiles();
      setPackages(packages);
    } catch (e) {
      setError(`加载失败：${String(e)}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const onDelete = async (pkg: PackageInfo) => {
    if (!window.confirm(`删除「${pkg.product_name}」的导出包？此操作不可恢复。`)) return;
    try {
      await deletePackage(pkg.task_id);
      setPackages((prev) => prev.filter((p) => p.task_id !== pkg.task_id));
      if (expanded === pkg.task_id) setExpanded(null);
    } catch (e) {
      alert(`删除失败：${String(e)}`);
    }
  };

  return (
    <main className="pb-24">
      <Nav />

      <div className="mx-auto max-w-6xl px-6">
        {/* ---------- 页头 ---------- */}
        <header className="mt-10 flex animate-fade-up items-end justify-between gap-4">
          <div>
            <p className="eyebrow">Files · 文件管理</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight text-ink-900">文件管理</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-ink-500">
              所有生成的上架包已落盘保存（重启不丢）：JSON 导出包 + 各平台后台导入表 + 生成主图
            </p>
          </div>
          <button onClick={load} className="btn-ghost shrink-0">
            刷新
          </button>
        </header>

        {error && (
          <div className="mt-6 rounded-lg bg-red-50 px-4 py-3 font-mono text-xs tracking-[0.04em] text-red-600">
            [ERROR] {error}
          </div>
        )}

        {loading && packages.length === 0 ? (
          <p className="py-24 text-center font-mono text-xs uppercase tracking-[0.08em] text-ink-400">
            <span className="mr-2 inline-block h-1.5 w-1.5 animate-pulse-dot rounded-full bg-brand-500" />
            Loading · 加载中…
          </p>
        ) : packages.length === 0 ? (
          <div className="card mt-8 p-10 text-center">
            <p className="text-sm text-ink-500">还没有已生成的上架包</p>
            <Link href="/" className="mt-3 inline-block text-sm font-medium text-brand-700 transition duration-150 hover:text-brand-800 hover:underline">
              去生成第一个 →
            </Link>
          </div>
        ) : (
          <div className="mt-8 space-y-3">
            {packages.map((pkg) => (
              <div key={pkg.task_id} className="card animate-fade-up overflow-hidden transition duration-150 hover:shadow-sm">
                <div className="flex items-center gap-4 px-5 py-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-semibold text-ink-900">{pkg.product_name}</span>
                      {pkg.revised_total > 0 && (
                        <span className="shrink-0 rounded-md bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-600">
                          自愈修订 ×{pkg.revised_total}
                        </span>
                      )}
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2 font-mono text-xs tabular-nums text-ink-500">
                      <span>{pkg.task_id}</span>
                      <span className="text-ink-300">·</span>
                      <span>{fmtTime(pkg.done_at || pkg.created_at)}</span>
                      <span className="text-ink-300">·</span>
                      <span>{fmtSize(pkg.total_size)}</span>
                      <span className="text-ink-300">·</span>
                      <span>
                        {pkg.platforms_done.filter((p) => p.passed).length}/{pkg.platforms_done.length} 平台合规
                      </span>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    {pkg.platforms.map((p) => {
                      const meta = PLATFORM_META.find((m) => m.key === p);
                      return (
                        <span
                          key={p}
                          className="flex items-center gap-1.5 rounded-md bg-ink-100 px-2.5 py-1 text-xs text-ink-600"
                        >
                          <span className="h-1.5 w-1.5 rounded-full" style={{ background: meta?.dot }} />
                          {meta?.name || p}
                        </span>
                      );
                    })}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Link
                      href={`/result/${pkg.task_id}`}
                      className="btn-ghost !px-3 !py-1.5 !text-xs"
                    >
                      查看结果
                    </Link>
                    <a
                      href={zipUrl(pkg.task_id)}
                      className="btn-primary !px-3 !py-1.5 !text-xs"
                    >
                      整包下载
                    </a>
                    <button
                      onClick={() => onDelete(pkg)}
                      className="rounded-md px-3 py-1.5 text-xs font-medium text-red-600 transition duration-150 hover:bg-red-50"
                    >
                      删除
                    </button>
                    <button
                      onClick={() => setExpanded(expanded === pkg.task_id ? null : pkg.task_id)}
                      className="rounded-md px-2 py-1.5 text-xs text-ink-400 transition duration-150 hover:bg-ink-50 hover:text-ink-700"
                    >
                      {expanded === pkg.task_id ? "收起" : "文件"}
                    </button>
                  </div>
                </div>

                {expanded === pkg.task_id && (
                  <div className="border-t border-ink-100 bg-ink-50/60 px-5 py-3">
                    {pkg.files.length === 0 ? (
                      <p className="py-2 text-xs text-ink-400">该包暂无文件（可能仍在生成中）</p>
                    ) : (
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        {pkg.files.map((f) => {
                          const meta = KIND_META[f.kind] || { label: f.kind, cls: "bg-ink-100 text-ink-600" };
                          const url = fileDownloadUrl(pkg.task_id, f.name);
                          return (
                            <a
                              key={f.name}
                              href={url}
                              className="flex items-center gap-3 rounded-lg bg-white px-3 py-2 ring-1 ring-ink-100 transition duration-150 hover:ring-brand-300"
                            >
                              {f.kind === "image" ? (
                                // eslint-disable-next-line @next/next/no-img-element
                                <img
                                  src={url}
                                  alt={f.name}
                                  className="h-9 w-9 shrink-0 rounded-lg border border-ink-100 object-cover"
                                />
                              ) : (
                                <span
                                  className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-[10px] font-bold ${meta.cls}`}
                                >
                                  {f.kind === "json" ? "JSON" : "CSV"}
                                </span>
                              )}
                              <span className="min-w-0 flex-1">
                                <span className="block truncate font-mono text-xs text-ink-700">{f.name}</span>
                                <span className="font-mono text-[11px] tabular-nums text-ink-400">{fmtSize(f.size)}</span>
                              </span>
                              <span className={`shrink-0 rounded-md px-2 py-0.5 text-xs ${meta.cls}`}>
                                {meta.label}
                              </span>
                            </a>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
