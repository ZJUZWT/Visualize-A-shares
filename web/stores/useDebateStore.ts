import { create } from "zustand";
import type {
  DebateEntry, JudgeVerdict, DebateStatus,
  ObserverState, RoleState, DebateReplayRecord,
} from "@/types/debate";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export type TranscriptItem =
  | { type: "entry"; data: DebateEntry }
  | { type: "round_divider"; round: number; is_final: boolean }
  | { type: "system"; text: string }
  | { type: "loading"; id: string };

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

  startDebate: (code: string, maxRounds: number) => Promise<void>;
  loadReplay: (debateId: string) => Promise<void>;
  reset: () => void;
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
  }),

  startDebate: async (code, maxRounds) => {
    get().reset();
    set({ status: "debating" });

    try {
      const res = await fetch(`${API_BASE}/api/v1/debate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, max_rounds: maxRounds }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        set({ error: err.detail ?? "请求失败", status: "idle" });
        return;
      }

      const reader = res.body!.getReader();
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

    case "debate_entry": {
      const entry = data as unknown as DebateEntry;
      if (DEBATERS.includes(entry.role)) {
        const roleState = {
          ...state.roleState,
          [entry.role]: {
            stance: entry.stance,
            confidence: entry.confidence,
            conceded: entry.stance === "concede",
          },
        };
        set({
          roleState,
          transcript: [...state.transcript, { type: "entry", data: entry }],
        });
      } else if (OBSERVERS.includes(entry.role)) {
        const observerState = {
          ...state.observerState,
          [entry.role]: {
            speak: true,
            argument: entry.argument,
            retail_sentiment_score: entry.retail_sentiment_score ?? undefined,
          },
        };
        set({
          observerState,
          _observerSpokenThisRound: { ...state._observerSpokenThisRound, [entry.role]: true },
        });
      }
      break;
    }

    case "data_fetching": {
      const loadingId = `loading_${Date.now()}`;
      set({ transcript: [...state.transcript, { type: "loading", id: loadingId }] });
      break;
    }

    case "data_ready": {
      set({
        transcript: state.transcript.filter(
          (item, idx) =>
            !(item.type === "loading" && idx === state.transcript.length - 1)
        ),
      });
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
      set({ judgeVerdict: data as unknown as JudgeVerdict, status: "completed" });
      break;
    }

    case "error": {
      const msg = (data.message as string) ?? "辩论出错";
      set({ error: msg, status: "idle" });
      break;
    }
  }
}
