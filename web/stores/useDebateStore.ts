import { create } from "zustand";
import type {
  DebateEntry, JudgeVerdict, DebateStatus,
  ObserverState, RoleState, DebateReplayRecord, RoundEval,
} from "@/types/debate";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

// 模块级变量，不放入 Zustand state，避免序列化问题
let _abortController: AbortController | null = null;

export type TranscriptItem =
  | { id: string; type: "entry"; data: DebateEntry }
  | { id: string; type: "round_divider"; round: number; is_final: boolean }
  | { id: string; type: "system"; text: string }
  | { id: string; type: "streaming"; role: string; round: number | null; tokens: string }
  | { id: string; type: "data_request"; requested_by: string; action: string; status: "pending" | "done" | "failed"; result_summary?: string; duration_ms?: number }
  | { id: string; type: "blackboard_data"; debateId: string; target: string; participants: string[] }
  | { id: string; type: "round_eval"; data: RoundEval }
  | { id: string; type: "industry_cognition"; industry: string; summary: string; cycle_position: string; traps_count: number; cached: boolean; loading: boolean; error?: boolean };

export interface BlackboardItem {
  id: string;
  source: "public" | "bull_expert" | "bear_expert";
  engine: string;
  action: string;
  title: string;
  status: "pending" | "done" | "failed";
  result_summary?: string;
  round: number;
}

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
  blackboardItems: BlackboardItem[];

  startDebate: (code: string, maxRounds: number) => Promise<void>;
  loadReplay: (debateId: string) => Promise<void>;
  reset: () => void;
  stopDebate: () => void;
}

const INITIAL_ROLE_STATE: RoleState = { stance: null, confidence: 0.5, inner_confidence: null, judge_confidence: null, conceded: false };
const OBSERVERS = ["retail_investor", "smart_money"];
const DEBATERS = ["bull_expert", "bear_expert"];

function _summarize(val: unknown): string {
  if (typeof val === "string") return val.slice(0, 300);
  try { return JSON.stringify(val).slice(0, 300); } catch { return String(val).slice(0, 300); }
}

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
  blackboardItems: [],

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
    blackboardItems: [],
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
          transcript.push({ id: `round_${entry.round}`, type: "round_divider", round: entry.round, is_final: false });
          lastRound = entry.round;
        }
        if (DEBATERS.includes(entry.role) || OBSERVERS.includes(entry.role)) {
          transcript.push({ id: `entry_${entry.role}_${entry.round}`, type: "entry", data: entry });
        }
      }

      const roleState: Record<string, RoleState> = {};
      for (const entry of (blackboard.transcript ?? []) as DebateEntry[]) {
        if (DEBATERS.includes(entry.role)) {
          roleState[entry.role] = {
            stance: entry.stance,
            confidence: entry.confidence,
            inner_confidence: entry.inner_confidence ?? null,
            judge_confidence: null,
            conceded: entry.stance === "concede",
          };
        }
      }
      // Apply judge_confidence from round_evals (last round wins)
      for (const re of (blackboard.round_evals ?? []) as RoundEval[]) {
        if (roleState["bull_expert"]) roleState["bull_expert"].judge_confidence = re.bull.judge_confidence;
        if (roleState["bear_expert"]) roleState["bear_expert"].judge_confidence = re.bear.judge_confidence;
      }

      // Build round_eval transcript items
      const roundEvalItems: TranscriptItem[] = (blackboard.round_evals ?? []).map((re: RoundEval) => ({
        id: `round_eval_${re.round}`,
        type: "round_eval" as const,
        data: re,
      }));

      // 从 blackboard 重建 blackboardItems
      const ACTION_TITLE: Record<string, string> = {
        get_stock_info: "股票基本信息", get_daily_history: "日线行情",
        get_news: "最新新闻", get_announcements: "公告",
        get_factor_scores: "因子评分", get_technical_indicators: "技术指标",
        get_money_flow: "资金流向", get_northbound_holding: "北向持仓",
        get_margin_balance: "融资融券", get_turnover_rate: "换手率",
        get_cluster_for_stock: "聚类分析", get_financials: "财务数据",
        get_restrict_stock_unlock: "限售解禁", get_signal_history: "信号历史",
      };
      const blackboardItems: BlackboardItem[] = [];
      // 公用初始数据（存在 facts 中）
      const INITIAL_ACTIONS: [string, string][] = [
        ["get_stock_info", "data"], ["get_daily_history", "data"], ["get_news", "info"],
      ];
      for (const [action, engine] of INITIAL_ACTIONS) {
        const hasFact = blackboard.facts && action in blackboard.facts;
        blackboardItems.push({
          id: `public_${action}`,
          source: "public",
          engine,
          action,
          title: ACTION_TITLE[action] ?? action,
          status: hasFact ? "done" : "failed",
          result_summary: hasFact ? _summarize(blackboard.facts[action]) : undefined,
          round: 0,
        });
      }
      // 专家数据请求
      for (const dr of (blackboard.data_requests ?? []) as Array<{
        requested_by: string; engine: string; action: string;
        status: string; result?: unknown; round: number;
      }>) {
        const source = (dr.requested_by === "bull_expert" || dr.requested_by === "bear_expert")
          ? dr.requested_by : "public";
        blackboardItems.push({
          id: `${dr.requested_by}_${dr.action}_${dr.round}`,
          source: source as BlackboardItem["source"],
          engine: dr.engine,
          action: dr.action,
          title: ACTION_TITLE[dr.action] ?? dr.action,
          status: dr.status as BlackboardItem["status"],
          result_summary: dr.result ? _summarize(dr.result) : undefined,
          round: dr.round,
        });
      }

      set({
        transcript: [...transcript, ...roundEvalItems],
        roleState,
        blackboardItems,
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
      const bbItem: TranscriptItem = {
        id: `blackboard_${data.debate_id}`,
        type: "blackboard_data",
        debateId: data.debate_id as string,
        target: data.target as string,
        participants: data.participants as string[],
      };
      set({ roleState, observerState, transcript: [bbItem] });
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
          { id: `round_${round}`, type: "round_divider", round, is_final },
        ],
      });
      break;
    }

    case "debate_token": {
      const { role, round, tokens } = data as { role: string; round: number | null; tokens: string };
      const streamId = `streaming_${role}_${round ?? "null"}`;
      const existing = state.transcript.findIndex(
        (item) => item.type === "streaming" && item.role === role && item.round === round
      );
      if (existing >= 0) {
        const updated = [...state.transcript];
        const item = updated[existing] as { id: string; type: "streaming"; role: string; round: number | null; tokens: string };
        updated[existing] = { ...item, tokens: item.tokens + tokens };
        set({ transcript: updated });
      } else {
        set({ transcript: [...state.transcript, { id: streamId, type: "streaming", role, round, tokens }] });
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
      // 如果 streaming 气泡已有内容，强制 speak=true，防止内容被 speak=false 清掉
      const streamingHasContent = idx >= 0 &&
        (state.transcript[idx] as Extract<TranscriptItem, { type: "streaming" }>).tokens.trim().length > 0;
      const finalEntry = streamingHasContent && !entry.speak
        ? { ...entry, speak: true }
        : entry;
      const entryId = idx >= 0 ? state.transcript[idx].id : `entry_${entry.role}_${entry.round}`;
      const newTranscript = idx >= 0
        ? [...state.transcript.slice(0, idx), { id: entryId, type: "entry" as const, data: finalEntry }, ...state.transcript.slice(idx + 1)]
        : [...state.transcript, { id: entryId, type: "entry" as const, data: finalEntry }];

      if (DEBATERS.includes(entry.role)) {
        set({
          transcript: newTranscript,
          roleState: {
            ...state.roleState,
            [entry.role]: {
              stance: entry.stance,
              confidence: entry.confidence,
              inner_confidence: entry.inner_confidence ?? null,
              judge_confidence: state.roleState[entry.role]?.judge_confidence ?? null,
              conceded: entry.stance === "concede",
            },
          },
        });
      } else if (OBSERVERS.includes(entry.role)) {
        set({
          transcript: newTranscript,
          observerState: {
            ...state.observerState,
            [entry.role]: { speak: finalEntry.speak, argument: finalEntry.argument, retail_sentiment_score: finalEntry.retail_sentiment_score ?? undefined },
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
        transcript: [...state.transcript, { id: request_id, type: "data_request", requested_by, action, status: "pending" }],
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
        const item = updated[existing] as { id: string; type: "streaming"; role: string; round: number | null; tokens: string };
        updated[existing] = { ...item, tokens: item.tokens + tokens };
        set({ transcript: updated });
      } else {
        set({ transcript: [...state.transcript, { id: "streaming_judge", type: "streaming", role: "judge", round: null, tokens }] });
      }
      break;
    }

    case "judge_round_eval": {
      const roundEval = data as unknown as RoundEval;
      const updatedRoleState = { ...state.roleState };
      if (updatedRoleState["bull_expert"]) {
        updatedRoleState["bull_expert"] = {
          ...updatedRoleState["bull_expert"],
          judge_confidence: roundEval.bull.judge_confidence,
        };
      }
      if (updatedRoleState["bear_expert"]) {
        updatedRoleState["bear_expert"] = {
          ...updatedRoleState["bear_expert"],
          judge_confidence: roundEval.bear.judge_confidence,
        };
      }
      set({
        roleState: updatedRoleState,
        transcript: [
          ...state.transcript,
          { id: `round_eval_${roundEval.round}`, type: "round_eval", data: roundEval },
        ],
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
          { id: `system_end_${rounds}`, type: "system", text: `${reasonText} · 共 ${rounds} 轮` },
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

    case "blackboard_update": {
      const item: BlackboardItem = {
        id: data.request_id as string,
        source: data.source as BlackboardItem["source"],
        engine: data.engine as string,
        action: data.action as string,
        title: data.title as string,
        status: data.status as BlackboardItem["status"],
        result_summary: data.result_summary as string | undefined,
        round: data.round as number,
      };
      const current = get().blackboardItems;
      const existing = current.findIndex(i => i.id === item.id);
      if (existing >= 0) {
        const updated = [...current];
        updated[existing] = item;
        set({ blackboardItems: updated });
      } else {
        set({ blackboardItems: [...current, item] });
      }
      break;
    }

    case "industry_cognition_start": {
      const industry = data.industry as string;
      const cached = data.cached as boolean;
      set({
        transcript: [...state.transcript, {
          id: "industry_cognition",
          type: "industry_cognition",
          industry,
          summary: "",
          cycle_position: "",
          traps_count: 0,
          cached,
          loading: true,
        }],
      });
      break;
    }

    case "industry_cognition_done": {
      const ic = data as { industry: string; summary: string; cycle_position: string; traps_count: number; cached: boolean; error?: boolean };
      set({
        transcript: state.transcript.map((item) =>
          item.type === "industry_cognition"
            ? { ...item, summary: ic.summary, cycle_position: ic.cycle_position, traps_count: ic.traps_count, loading: false, error: ic.error }
            : item
        ),
      });
      break;
    }

    case "initial_data_complete":
      // 静默处理，无需 UI 状态变更
      break;

    case "error": {
      const msg = (data.message as string) ?? "辩论出错";
      set({ error: msg, status: "idle" });
      break;
    }
  }
}
