"use client";

import { useEffect, useRef } from "react";

/**
 * 退避策略（针对「连续失败」的等待时间）：
 * - fixed       每次失败后仍等待 interval
 * - linear      interval × 连续失败次数
 * - exponential interval × 2^连续失败次数（首次失败 = 2 × interval），封顶 maxDelay
 * 成功后回到固定 interval，且连续失败计数清零。
 */
export type PollingBackoff = "fixed" | "linear" | "exponential";

export interface UseTaskPollingOptions<T> {
  /** 每次轮询执行的请求：resolve 视为一次成功，reject 视为一次失败。 */
  fetchFn: () => Promise<T>;
  /** 基础轮询间隔（毫秒），默认 1500。 */
  interval?: number;
  /** 最大连续失败次数（任一次成功即清零重计）；达到后停止轮询并触发 onError(err, true)。 */
  maxAttempts?: number;
  /** 失败后的退避策略，默认 "fixed"。 */
  backoff?: PollingBackoff;
  /** 单次重试等待上限（毫秒），默认 30000。 */
  maxDelay?: number;
  /** 是否立即发起第一次请求，默认 true；false 时首个请求在 interval 之后发出。 */
  immediate?: boolean;
  /** 为 false 时不轮询（已在运行的轮询随之停止并清理定时器），默认 true。 */
  enabled?: boolean;
  /** 终态判定：返回 true 则停止轮询并触发 onDone；不提供则持续轮询（直到超限/停用）。 */
  isDone?: (value: T) => boolean;
  /** 每次成功获取时触发（含到达终态的那次）。 */
  onUpdate?: (value: T) => void;
  /** 到达终态时触发。 */
  onDone?: (value: T) => void;
  /** 每次失败触发；gaveUp=true 表示已达 maxAttempts 上限、轮询就此停止。 */
  onError?: (error: unknown, gaveUp: boolean) => void;
}

/**
 * 统一任务轮询 hook。
 *
 * - 内部用「链式 setTimeout」驱动：上一次请求完成后才排下一次，天然不重入、不堆积。
 * - 自带失败退避、连续失败上限（maxAttempts）与终态停止（isDone）。
 * - 组件卸载或 enabled 置 false 时清理挂起的定时器，并忽略在途请求的回调。
 * - fetchFn / 各回调通过 ref 读取最新值：传内联函数或依赖更新都不会打断轮询节奏。
 */
export function useTaskPolling<T>(options: UseTaskPollingOptions<T>): void {
  // 始终读取最新的 options，避免回调闭包过期
  const optsRef = useRef(options);
  useEffect(() => {
    optsRef.current = options;
  });

  const enabled = options.enabled !== false;

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let failures = 0; // 连续失败次数（成功清零）

    const run = async () => {
      if (cancelled) return;
      const o = optsRef.current;
      try {
        const value = await o.fetchFn();
        if (cancelled) return;
        failures = 0;
        o.onUpdate?.(value);
        if (o.isDone?.(value)) {
          o.onDone?.(value);
          return; // 终态：停止轮询
        }
        timer = setTimeout(run, o.interval ?? 1500);
      } catch (error) {
        if (cancelled) return;
        failures += 1;
        const gaveUp = o.maxAttempts != null && failures >= o.maxAttempts;
        o.onError?.(error, gaveUp);
        if (gaveUp) return; // 连续失败超限：停止轮询
        const interval = o.interval ?? 1500;
        let delay: number;
        switch (o.backoff ?? "fixed") {
          case "linear":
            delay = interval * failures;
            break;
          case "exponential":
            delay = interval * 2 ** failures;
            break;
          default:
            delay = interval;
        }
        timer = setTimeout(run, Math.min(delay, o.maxDelay ?? 30000));
      }
    };

    if (optsRef.current.immediate === false) {
      timer = setTimeout(run, optsRef.current.interval ?? 1500);
    } else {
      void run();
    }

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [enabled]);
}
