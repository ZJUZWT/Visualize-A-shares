import type { BrainRun } from "../types.ts";

type MaybePromise<T = void> = T | Promise<T>;

export interface BrainRunPollerHandle {
  stop: () => void;
  done: Promise<void>;
}

interface StartBrainRunPollerOptions {
  loadRun: (signal: AbortSignal) => Promise<BrainRun>;
  onUpdate?: (run: BrainRun) => MaybePromise;
  onTerminal?: (run: BrainRun) => MaybePromise;
  onError?: (error: unknown) => MaybePromise;
  onTimeout?: () => MaybePromise;
  intervalMs?: number;
  requestTimeoutMs?: number;
  maxPollMs?: number;
  maxConsecutiveErrors?: number;
  now?: () => number;
  delay?: (ms: number) => Promise<void>;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function startBrainRunPoller(
  options: StartBrainRunPollerOptions
): BrainRunPollerHandle {
  const intervalMs = options.intervalMs ?? 3_000;
  const requestTimeoutMs = options.requestTimeoutMs ?? 15_000;
  const maxPollMs = options.maxPollMs ?? 5 * 60 * 1_000;
  const maxConsecutiveErrors = options.maxConsecutiveErrors ?? 5;
  const now = options.now ?? Date.now;
  const delay = options.delay ?? sleep;
  const startedAt = now();
  let stopped = false;
  let consecutiveErrors = 0;
  let activeController: AbortController | null = null;

  const done = (async () => {
    while (!stopped) {
      if (now() - startedAt > maxPollMs) {
        stopped = true;
        await options.onTimeout?.();
        return;
      }

      try {
        const controller = new AbortController();
        activeController = controller;
        const timeoutId = setTimeout(() => {
          controller.abort(new Error("brain run poll request timed out"));
        }, requestTimeoutMs);
        let run: BrainRun;
        try {
          run = await options.loadRun(controller.signal);
        } finally {
          clearTimeout(timeoutId);
          if (activeController === controller) {
            activeController = null;
          }
        }
        if (stopped) {
          return;
        }

        consecutiveErrors = 0;
        await options.onUpdate?.(run);
        if (stopped) {
          return;
        }

        if (run.status !== "running") {
          stopped = true;
          await options.onTerminal?.(run);
          return;
        }
      } catch (error) {
        activeController = null;
        if (stopped) {
          return;
        }

        consecutiveErrors += 1;
        if (consecutiveErrors >= maxConsecutiveErrors) {
          stopped = true;
          await options.onError?.(error);
          return;
        }
      }

      await delay(intervalMs);
    }
  })();

  return {
    stop() {
      stopped = true;
      activeController?.abort(new Error("brain run poll stopped"));
      activeController = null;
    },
    done,
  };
}
