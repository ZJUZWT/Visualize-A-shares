import { create } from "zustand";
import type {
  DebateEntry, JudgeVerdict, DebateStatus,
  ObserverState, RoleState, DebateReplayRecord,
} from "@/types/debate";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

// 模块级变量，不放入 Zustand state，避免序列化问题
let _abortController: AbortController | null = null;

export type TranscriptItem =
  | { type: "entry"; data: DebateEntry }
  | { type: "round_divider"; round: number; is_final: boolean }
  | { type: "system"; text: string }
  | { type: "streaming"; role: string; round: number | null; tokens: string }
  | { type: "data_request"; id: string; requested_by: string; action: string; status: "pending" | "done" | "failed"; result_summary?: string; duration_ms?: number };

interface DebateStore {
  status: DebateStatus;
  transcript: TranscriptItem[];
  observerState: Record<string, ObserverState>;
  roleState: Record<string, RoleState>;
  currentRound: number;
  judgeVerdict: JudgeVerdict | null;
  isReplayMode: boolean;
  error: string | null;
  _observerSpokenThisRound: Record<string, boolean>;
  currentTarget: string | null;

  startDebate: (code: string, maxRounds: number) => Promise<void>;
  loadReplay: (debateId: string) => Promise<void>;
  reset: () => void;
  stopDebate: () => void;
}

const INITIAL_ROLE_STATE: RoleState = { stance: null, confidence: 0.5, conceded: false };
const OBSERVERS = ["retail_investor", "smart_money"];
const DEBATERS = ["bull_expert", "bear_expert"];

export const useDebateStore = create<DebateStore>((set, get) => ({
  status: "idle",
  transcript: [],
  observerState: {},
  roleState: {},
  currentRound: 0,
  judgeVerdict: null,
  isReplayMode: false,
  error: null,
  _observerSpokenThisRound: {},
  currentTarget: null,

  reset: () => set({
    status: "idle",
    transcript: [],
    observerState: {},
    roleState: {},
    currentRound: 0,
    judgeVerdict: null,
    isReplayMode: false,
    error: null,
    _observerSpokenThisRound: {},
    currentTarget: null,
  }),

  stopDebate: () => {
    _abortController?.abort();
    _abortController = null;
    set({ status: "stopped" });
  },

  startDebate: async (code, maxRounds) => {
    get().reset();
    _abortController = new AbortController();
    set({ status: "debating", currentTarget: code });

    try {
      const res = await fetch(`${API_BASE}/api/v1/debate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, max_rounds: maxRounds }),
        signal: _abortController.signal,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        set({ error: err.detail ?? "请求失败", status: "idle" });
        return;
      }

      if (!res.body) {
        set({ error: "响应体为空", status: "idle" });
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";

        for (const chunk of chunks) {
          const lines = chunk.split("\n");
          let eventType = "";
          let dataStr = "";
          for (const line of lines) {
            if (line.startsWith("event: ")) eventType = line.slice(7).trim();
            if (line.startsWith("data: ")) dataStr = line.slice(6).trim();
          }
          if (!eventType || !dataStr) continue;

          try {
            const data = JSON.parse(dataStr);
            _handleSSEEvent(eventType, data, set, get);
          } catch {
            // 忽略解析失败的事件
          }
        }
      }
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      const msg = e instanceof Error ? e.message : "连接失败";
      set({ error: msg, status: "idle" });
    }
  },

  loadReplay: async (debateId) => {
    get().reset();
    set({ isReplayMode: true });

    try {
      const res = await fetch(`${API_BASE}/api/v1/debate/${debateId}`);
      if (!res.ok) {
        set({ error: "加载回放失败", isReplayMode: false });
        return;
      }
      const record: DebateReplayRecord = await res.json();
      const blackboard = JSON.parse(record.blackboard_json);
      const verdict: JudgeVerdict = JSON.parse(record.judge_verdict_json);

      const transcript: TranscriptItem[] = [];
      let lastRound = 0;
      for (const entry of (blackboard.transcript ?? []) as DebateEntry[]) {
        if (entry.round !== lastRound) {
          transcript.push({ type: "round_divider", round: entry.round, is_final: false });
          lastRound = entry.round;
        }
        if (DEBATERS.includes(entry.role)) {
          transcript.push({ type: "entry", data: entry });
        }
      }

      const roleState: Record<string, RoleState> = {};
      for (const entry of (blackboard.transcript ?? []) as DebateEntry[]) {
        if (DEBATERS.includes(entry.role)) {
          roleState[entry.role] = {
            stance: entry.stance,
            confidence: entry.confidence,
            conceded: entry.stance === "concede",
          };
        }
      }

      set({
        transcript,
        roleState,
        judgeVerdict: verdict,
        status: "completed",
        currentRound: record.rounds_completed,
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "回放加载失败";
      set({ error: msg, isReplayMode: false });
    }
  },
}));

function _handleSSEEvent(
  eventType: string,
  data: Record<string, unknown>,
  set: (partial: Partial<DebateStore>) => void,
  get: () => DebateStore,
) {
  const state = get();
  if (state.status === "stopped") return;

  switch (eventType) {
    case "debate_start": {
      const roleState: Record<string, RoleState> = {};
      for (const role of DEBATERS) roleState[role] = { ...INITIAL_ROLE_STATE };
      const observerState: Record<string, ObserverState> = {};
      for (const obs of OBSERVERS) observerState[obs] = { speak: false, argument: "" };
      set({ roleState, observerState });
      break;
    }

    case "debate_round_start": {
      const round = data.round as number;
      const is_final = data.is_final as boolean;

      const prevSpoken = state._observerSpokenThisRound;
      const observerState = { ...state.observerState };
      for (const obs of OBSERVERS) {
        if (!prevSpoken[obs]) {
          observerState[obs] = { ...observerState[obs], speak: false, argument: "" };
        }
      }

      set({
        status: is_final ? "final_round" : "debating",
        currentRound: round,
        observerState,
        _observerSpokenThisRound: {},
        transcript: [
          ...state.transcript,
          { type: "round_divider", round, is_final },
        ],
      });
      break;
    }

    case "debate_token": {
      const { role, round, tokens } = data as { role: string; round: number | null; tokens: string };
      const existing = state.transcript.findIndex(
        (item) => item.type === "streaming" && item.role === role && item.round === round
      );
      if (existing >= 0) {
        const updated = [...state.transcript];
        const item = updated[existing] as { type: "streaming"; role: string; round: number | null; tokens: string };
        updated[existing] = { ...item, tokens: item.tokens + tokens };
        set({ transcript: updated });
      } else {
        set({ transcript: [...state.transcript, { type: "streaming", role, round, tokens }] });
      }
      break;
    }

    case "debate_entry_complete": {
      const entry = data as unknown as DebateEntry;
      const idx = (() => {
        for (let i = state.transcript.length - 1; i >= 0; i--) {
          const item = state.transcript[i];
          if (item.type === "streaming" && item.role === entry.role && item.round === entry.round) return i;
        }
        return -1;
      })();
      const newTranscript = idx >= 0
        ? [...state.transcript.slice(0, idx), { type: "entry" as const, data: entry }, ...state.transcript.slice(idx + 1)]
        : [...state.transcript, { type: "entry" as const, data: entry }];

      if (DEBATERS.includes(entry.role)) {
        set({
          transcript: newTranscript,
          roleState: {
            ...state.roleState,
            [entry.role]: { stance: entry.stance, confidence: entry.confidence, conceded: entry.stance === "concede" },
          },
        });
      } else if (OBSERVERS.includes(entry.role)) {
        set({
          transcript: newTranscript,
          observerState: {
            ...state.observerState,
            [entry.role]: { speak: entry.speak, argument: entry.argument, retail_sentiment_score: entry.retail_sentiment_score ?? undefined },
          },
          _observerSpokenThisRound: { ...state._observerSpokenThisRound, [entry.role]: true },
        });
      } else {
        set({ transcript: newTranscript });
      }
      break;
    }

    case "data_request_start": {
      const { request_id, requested_by, action } = data as { request_id: string; requested_by: string; action: string };
      set({
        transcript: [...state.transcript, { type: "data_request", id: request_id, requested_by, action, status: "pending" }],
      });
      break;
    }

    case "data_request_done": {
      const { request_id, status, result_summary, duration_ms } = data as { request_id: string; status: "done" | "failed"; result_summary: string; duration_ms: number };
      set({
        transcript: state.transcript.map((item) =>
          item.type === "data_request" && item.id === request_id
            ? { ...item, status, result_summary, duration_ms }
            : item
        ),
      });
      break;
    }

    case "judge_token": {
      const { tokens } = data as { tokens: string };
      const existing = state.transcript.findIndex(
        (item) => item.type === "streaming" && item.role === "judge"
      );
      if (existing >= 0) {
        const updated = [...state.transcript];
        const item = updated[existing] as { type: "streaming"; role: string; round: number | null; tokens: string };
        updated[existing] = { ...item, tokens: item.tokens + tokens };
        set({ transcript: updated });
      } else {
        set({ transcript: [...state.transcript, { type: "streaming", role: "judge", round: null, tokens }] });
      }
      break;
    }

    case "debate_end": {
      const reason = data.reason as string;
      const rounds = data.rounds_completed as number;
      const reasonText = {
        bull_conceded: "多头认输",
        bear_conceded: "空头认输",
        both_conceded: "双方认输",
        max_rounds: "达到最大轮次",
      }[reason] ?? reason;
      set({
        status: "judging",
        transcript: [
          ...state.transcript,
          { type: "system", text: `${reasonText} · 共 ${rounds} 轮` },
        ],
      });
      break;
    }

    case "judge_verdict": {
      const cleanedTranscript = state.transcript.filter(
        (item) => !(item.type === "streaming" && item.role === "judge")
      );
      set({ judgeVerdict: data as unknown as JudgeVerdict, status: "completed", transcript: cleanedTranscript });
      break;
    }

    case "error": {
      const msg = (data.message as string) ?? "辩论出错";
      set({ error: msg, status: "idle" });
      break;
    }
  }
}
