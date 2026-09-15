"use client";

import { useCallback, useEffect, useState } from "react";
import {
  PublishJob,
  fetchPublishJobs,
  publishShotUrl,
  publishTask,
} from "@/lib/api";
import { useTaskPolling } from "@/lib/useTaskPolling";

/** 执行器动作的展示元信息（与 publisher 的 steps[] action 对齐）。 */
const ACTION_LABEL: Record<string, string> = {
  open_page: "打开卖家后台",
  fill_fields: "填充表单字段",
  upload_image: "上传主图",
  submit: "提交上架",
  live_confirm: "确认上线",
};

const STATUS_META: Record<string, { label: string; cls: string }> = {
  queued: { label: "排队中", cls: "bg-ink-100 text-ink-500" },
  running: { label: "执行中", cls: "bg-brand-50 text-brand-700" },
  live: { label: "已上线", cls: "bg-green-50 text-green-700" },
  failed: { label: "失败", cls: "bg-red-50 text-red-600" },
};

function fmtClock(ts: number) {
  const d = new Date(ts * 1000);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(
    d.getSeconds()
  ).padStart(2, "0")}`;
}

/**
 * 上架闭环面板（PRD v0.3 · Feature 5）：
 * 确认上架（硬闸口）→ 执行器 steps[] 留痕回放（含截图）→ live URL。
 * 无留痕不执行；合规未通过禁止上架。
 */
export default function PublishPanel({
  taskId,
  platform,
  compliancePassed,
}: {
  taskId: string;
  platform: string;
  compliancePassed: boolean;
}) {
  const [job, setJob] = useState<PublishJob | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [traceOpen, setTraceOpen] = useState(true);

  /** 拉取本平台最新发布任务；失败时抛出，由初始加载 / 轮询 hook 决定如何提示。 */
  const fetchJob = useCallback(async (): Promise<PublishJob | null> => {
    const { jobs } = await fetchPublishJobs(taskId);
    return jobs.filter((j) => j.platform === platform)[0] || null;
  }, [taskId, platform]);

  // 初次进入面板：拉一次现有任务（失败静默，不影响面板展示）
  useEffect(() => {
    fetchJob()
      .then(setJob)
      .catch(() => {
        /* 后端暂不可达：等待后续动作 */
      });
  }, [fetchJob]);

  const running = job?.status === "queued" || job?.status === "running";

  // 执行中每 1.5s 轮询，直至 live / failed；失败指数退避，连续 20 次失败后停止并提示
  useTaskPolling({
    fetchFn: fetchJob,
    interval: 1500,
    immediate: false,
    backoff: "exponential",
    maxAttempts: 20,
    enabled: running,
    onUpdate: setJob,
    isDone: (j) => !!j && (j.status === "live" || j.status === "failed"),
    onError: (e, gaveUp) => {
      if (gaveUp) setError(`后端连接持续失败，已暂停执行状态刷新：${String(e)}`);
    },
  });

  async function onPublish() {
    setBusy(true);
    setError("");
    try {
      const res = await publishTask(taskId, platform);
      setJob(res.job);
      setConfirming(false);
      setTraceOpen(true);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const st = job ? STATUS_META[job.status] : null;

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between">
        <h2 className="eyebrow">自动上架</h2>
        {st && (
          <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${st.cls}`}>
            {running && <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-current" />}
            {st.label}
          </span>
        )}
      </div>

      {/* ---------- 未上架：硬闸口 ---------- */}
      {!job && !confirming && (
        <div className="mt-4">
          <p className="text-xs leading-5 text-ink-500">
            确认后由 AI 操作浏览器把本平台上架包自动填入卖家后台（演示环境），全程逐步留痕 + 截图，出错可回溯。
          </p>
          <button
            onClick={() => setConfirming(true)}
            disabled={!compliancePassed}
            className="btn-primary mt-3 w-full disabled:cursor-not-allowed disabled:opacity-50"
          >
            确认上架本平台
          </button>
          {!compliancePassed && (
            <p className="mt-2 text-xs text-red-500">合规未通过，禁止上架（先修复合规问题）</p>
          )}
        </div>
      )}

      {/* ---------- 二次确认（硬闸口，严禁无人值守上架） ---------- */}
      {confirming && !job && (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <p className="text-sm font-medium text-amber-800">确认执行自动上架？</p>
          <p className="mt-1.5 text-xs leading-5 text-amber-700">
            AI 将驱动浏览器完成填表与提交，每一步都会留痕截图；上架后经营数据自动回流，异常将触发进化提案。
          </p>
          <div className="mt-3 flex gap-2">
            <button onClick={() => setConfirming(false)} className="btn-ghost flex-1" disabled={busy}>
              取消
            </button>
            <button onClick={onPublish} className="btn-primary flex-1" disabled={busy}>
              {busy ? "已派发…" : "确认上架"}
            </button>
          </div>
          {error && (
            <p role="alert" className="mt-2 text-xs text-red-600">
              {error}
            </p>
          )}
        </div>
      )}

      {/* ---------- 执行中 / 已完成：留痕回放 ---------- */}
      {job && (
        <div className="mt-4">
          <div className="flex items-center justify-between font-mono text-[11px] tabular-nums text-ink-400">
            <span>{job.job_id}</span>
            <span>SKU {job.sku}</span>
          </div>

          {/* live 横幅 */}
          {job.status === "live" && job.live_url && (
            <a
              href={job.live_url}
              target="_blank"
              className="mt-3 flex items-center gap-2 rounded-xl border border-green-200 bg-green-50 px-4 py-3 transition hover:bg-green-100"
            >
              <span className="h-2 w-2 rounded-full bg-green-500 shadow-[0_0_0_3px_rgba(34,197,94,.2)]" />
              <span className="text-sm font-medium text-green-700">listing 已上线，查看卖家后台 live 页</span>
              <span className="ml-auto font-mono text-[11px] text-green-600">{job.listing_id} ↗</span>
            </a>
          )}

          {/* 失败信息 */}
          {job.status === "failed" && (
            <div className="mt-3 rounded-xl bg-red-50 px-4 py-3">
              <p className="text-sm font-medium text-red-600">上架失败（已重试 {job.attempts - 1} 次）</p>
              <p className="mt-1 break-all font-mono text-[11px] leading-5 text-red-500">{job.last_error}</p>
            </div>
          )}

          {/* 轮询超限提示：后端持续不可达时，执行状态不再自动刷新 */}
          {error && job.status !== "failed" && (
            <p role="alert" className="mt-3 rounded-xl bg-red-50 px-4 py-3 text-xs leading-5 text-red-600">
              {error}
            </p>
          )}

          {/* 执行留痕 */}
          <button
            onClick={() => setTraceOpen((v) => !v)}
            className="mt-4 flex w-full items-center justify-between text-left"
          >
            <span className="spec-label">Execution Trace · {job.steps.length} 步留痕</span>
            <span className="font-mono text-[11px] text-ink-300">{traceOpen ? "收起 −" : "展开 +"}</span>
          </button>

          {traceOpen && (
            <div className="mt-3">
              {job.steps.length === 0 && running && (
                <p className="flex items-center gap-2 text-xs text-ink-400">
                  <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-brand-500" />
                  执行器运行中，留痕生成后实时回传…
                </p>
              )}
              <ol className="space-y-3">
                {job.steps.map((s, i) => (
                  <li key={i} className="flex gap-3">
                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-brand-50 font-mono text-[10px] font-medium tabular-nums text-brand-700">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-2">
                        <p className="text-xs font-medium text-ink-800">
                          {ACTION_LABEL[s.action] || s.action}
                        </p>
                        <span className="shrink-0 font-mono text-[10px] tabular-nums text-ink-300">
                          {fmtClock(s.ts)}
                        </span>
                      </div>
                      <p className="mt-0.5 break-all text-[11px] leading-4 text-ink-400">{s.detail}</p>
                      {s.screenshot && (
                        <a href={publishShotUrl(job.job_id, s.screenshot)} target="_blank" className="mt-1.5 block">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={publishShotUrl(job.job_id, s.screenshot)}
                            alt={`留痕截图 ${i + 1}`}
                            className="w-full rounded-lg ring-1 ring-ink-100 transition hover:ring-brand-300"
                          />
                        </a>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
