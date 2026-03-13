/**
 * AI 聊天状态管理 (Zustand)
 *
 * 功能：
 * - 管理聊天消息列表和流式接收状态
 * - LLM 配置管理（provider/api_key/base_url/model）
 * - 自动从 useTerrainStore 提取上下文注入
 * - SSE 流式对话
 */

import { create } from "zustand";
import { useTerrainStore } from "./useTerrainStore";

const SSE_API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

// ─── Types ────────────────────────────────────────

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  isStreaming?: boolean;
}

export interface LLMConfig {
  provider: string;
  apiKey: string;
  baseUrl: string;
  model: string;
  temperature: number;
  maxTokens: number;
}

/** 预设的厂商配置 */
export const PROVIDER_PRESETS: Record<
  string,
  { label: string; baseUrl: string; models: string[]; provider: string }
> = {
  openai: {
    label: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    models: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    provider: "openai_compatible",
  },
  deepseek: {
    label: "DeepSeek",
    baseUrl: "https://api.deepseek.com/v1",
    models: ["deepseek-chat", "deepseek-reasoner"],
    provider: "openai_compatible",
  },
  qwen: {
    label: "通义千问",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    models: ["qwen-plus", "qwen-turbo", "qwen-max", "qwen-long"],
    provider: "openai_compatible",
  },
  kimi: {
    label: "Kimi (月之暗面)",
    baseUrl: "https://api.moonshot.cn/v1",
    models: ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
    provider: "openai_compatible",
  },
  glm: {
    label: "智谱 GLM",
    baseUrl: "https://open.bigmodel.cn/api/paas/v4",
    models: ["glm-4-plus", "glm-4", "glm-4-flash"],
    provider: "openai_compatible",
  },
  claude: {
    label: "Anthropic Claude",
    baseUrl: "https://api.anthropic.com",
    models: ["claude-sonnet-4-20250514", "claude-3-5-haiku-20241022"],
    provider: "anthropic",
  },
  custom: {
    label: "自定义",
    baseUrl: "",
    models: [],
    provider: "openai_compatible",
  },
};

interface ChatState {
  // ─── 聊天状态 ────────────────────
  messages: ChatMessage[];
  isStreaming: boolean;
  error: string | null;

  // ─── 面板状态 ────────────────────
  isPanelOpen: boolean;
  isConfigOpen: boolean;

  // ─── LLM 配置 ────────────────────
  llmConfig: LLMConfig;
  selectedPreset: string;

  // ─── Actions ─────────────────────
  togglePanel: () => void;
  toggleConfig: () => void;
  setSelectedPreset: (preset: string) => void;
  updateLLMConfig: (partial: Partial<LLMConfig>) => void;
  saveLLMConfig: () => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  clearMessages: () => void;
}

/** 从 localStorage 恢复配置 */
function loadSavedConfig(): LLMConfig {
  if (typeof window === "undefined") return getDefaultConfig();
  try {
    const saved = localStorage.getItem("stockterrain_llm_config");
    if (saved) {
      return { ...getDefaultConfig(), ...JSON.parse(saved) };
    }
  } catch {}
  return getDefaultConfig();
}

function getDefaultConfig(): LLMConfig {
  return {
    provider: "openai_compatible",
    apiKey: "",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
    temperature: 0.7,
    maxTokens: 2048,
  };
}

function loadSavedPreset(): string {
  if (typeof window === "undefined") return "openai";
  try {
    return localStorage.getItem("stockterrain_llm_preset") || "openai";
  } catch {
    return "openai";
  }
}

/** 从 terrain store 提取上下文用于注入 */
function extractTerrainContext() {
  const state = useTerrainStore.getState();
  const data = state.terrainData;
  if (!data) return {};

  // 构建 terrain_summary
  const stocks = data.stocks || [];
  const sorted = [...stocks].sort(
    (a, b) => (b.z_pct_chg ?? 0) - (a.z_pct_chg ?? 0)
  );
  const upCount = stocks.filter((s) => (s.z_pct_chg ?? 0) > 0).length;
  const downCount = stocks.filter((s) => (s.z_pct_chg ?? 0) < 0).length;
  const avgPctChg =
    stocks.length > 0
      ? stocks.reduce((sum, s) => sum + (s.z_pct_chg ?? 0), 0) / stocks.length
      : 0;

  const terrain_summary: Record<string, unknown> = {
    stock_count: data.stock_count,
    cluster_count: data.cluster_count,
    active_metric: data.active_metric,
    market_stats: {
      up_count: upCount,
      down_count: downCount,
      flat_count: stocks.length - upCount - downCount,
      avg_pct_chg: avgPctChg,
    },
    top_gainers: sorted.slice(0, 5).map((s) => ({
      code: s.code,
      name: s.name,
      pct_chg: s.z_pct_chg ?? 0,
    })),
    top_losers: sorted.slice(-5).reverse().map((s) => ({
      code: s.code,
      name: s.name,
      pct_chg: s.z_pct_chg ?? 0,
    })),
    cluster_summary: (data.clusters || []).slice(0, 8).map((c) => ({
      cluster_id: c.cluster_id,
      size: c.size,
      top_stocks: c.top_stocks?.slice(0, 3) || [],
    })),
  };

  // 选中的股票
  const selected = state.selectedStock;
  const selected_stock = selected
    ? {
        code: selected.code,
        name: selected.name,
        cluster_id: selected.cluster_id,
        z_pct_chg: selected.z_pct_chg,
        z_turnover_rate: selected.z_turnover_rate,
        z_volume: selected.z_volume,
        z_amount: selected.z_amount,
        z_pe_ttm: selected.z_pe_ttm,
        z_pb: selected.z_pb,
        z_rise_prob: selected.z_rise_prob,
        related_stocks: selected.related_stocks?.slice(0, 5),
      }
    : undefined;

  return { terrain_summary, selected_stock };
}

let messageCounter = 0;
function nextId() {
  return `msg_${Date.now()}_${++messageCounter}`;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isStreaming: false,
  error: null,

  isPanelOpen: false,
  isConfigOpen: false,

  llmConfig: loadSavedConfig(),
  selectedPreset: loadSavedPreset(),

  togglePanel: () => set((s) => ({ isPanelOpen: !s.isPanelOpen })),
  toggleConfig: () => set((s) => ({ isConfigOpen: !s.isConfigOpen })),

  setSelectedPreset: (preset: string) => {
    const p = PROVIDER_PRESETS[preset];
    if (!p) return;

    set((s) => ({
      selectedPreset: preset,
      llmConfig: {
        ...s.llmConfig,
        provider: p.provider,
        baseUrl: preset !== "custom" ? p.baseUrl : s.llmConfig.baseUrl,
        model: preset !== "custom" && p.models.length > 0 ? p.models[0] : s.llmConfig.model,
      },
    }));

    try {
      localStorage.setItem("stockterrain_llm_preset", preset);
    } catch {}
  },

  updateLLMConfig: (partial) =>
    set((s) => ({
      llmConfig: { ...s.llmConfig, ...partial },
    })),

  saveLLMConfig: async () => {
    const { llmConfig } = get();
    // 持久化到 localStorage
    try {
      localStorage.setItem(
        "stockterrain_llm_config",
        JSON.stringify(llmConfig)
      );
    } catch {}

    // 同步到后端
    try {
      await fetch(`${SSE_API_BASE}/api/v1/chat/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: llmConfig.provider,
          api_key: llmConfig.apiKey,
          base_url: llmConfig.baseUrl,
          model: llmConfig.model,
          temperature: llmConfig.temperature,
          max_tokens: llmConfig.maxTokens,
        }),
      });
    } catch (e) {
      console.warn("同步 LLM 配置到后端失败:", e);
    }
  },

  sendMessage: async (content: string) => {
    const { messages, llmConfig } = get();

    if (!llmConfig.apiKey) {
      set({ error: "请先配置 API Key（点击右下角 ⚙️ 设置按钮）" });
      return;
    }

    // 添加用户消息
    const userMsg: ChatMessage = {
      id: nextId(),
      role: "user",
      content,
      timestamp: Date.now(),
    };

    // 添加空的 assistant 消息（流式填充）
    const assistantMsg: ChatMessage = {
      id: nextId(),
      role: "assistant",
      content: "",
      timestamp: Date.now(),
      isStreaming: true,
    };

    set({
      messages: [...messages, userMsg, assistantMsg],
      isStreaming: true,
      error: null,
    });

    try {
      // 构建历史消息（最近 10 轮）
      const history = messages.slice(-20).map((m) => ({
        role: m.role,
        content: m.content,
      }));

      // 提取当前地形上下文
      const context = extractTerrainContext();

      const res = await fetch(`${SSE_API_BASE}/api/v1/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: content,
          history,
          terrain_summary: context.terrain_summary || null,
          selected_stock: context.selected_stock || null,
          override_config: {
            provider: llmConfig.provider,
            api_key: llmConfig.apiKey,
            base_url: llmConfig.baseUrl,
            model: llmConfig.model,
            temperature: llmConfig.temperature,
            max_tokens: llmConfig.maxTokens,
          },
        }),
      });

      if (!res.ok) {
        const errBody = await res.text();
        let detail = `HTTP ${res.status}`;
        try {
          detail = JSON.parse(errBody).detail || detail;
        } catch {}
        throw new Error(detail);
      }

      // SSE 流式读取
      const reader = res.body?.getReader();
      if (!reader) throw new Error("浏览器不支持流式读取");

      const decoder = new TextDecoder();
      let buffer = "";
      let fullContent = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";

        for (const eventBlock of events) {
          if (!eventBlock.trim()) continue;
          const lines = eventBlock.split("\n");
          let eventType = "";
          let eventData = "";

          for (const line of lines) {
            if (line.startsWith("event: ")) eventType = line.slice(7).trim();
            else if (line.startsWith("data: ")) eventData = line.slice(6);
          }

          if (!eventType || !eventData) continue;

          try {
            const parsed = JSON.parse(eventData);

            if (eventType === "token") {
              fullContent += parsed.content;
              // 更新 assistant 消息内容
              set((s) => ({
                messages: s.messages.map((m) =>
                  m.id === assistantMsg.id
                    ? { ...m, content: fullContent }
                    : m
                ),
              }));
            } else if (eventType === "done") {
              set((s) => ({
                messages: s.messages.map((m) =>
                  m.id === assistantMsg.id
                    ? {
                        ...m,
                        content: parsed.full_content || fullContent,
                        isStreaming: false,
                      }
                    : m
                ),
                isStreaming: false,
              }));
              return;
            } else if (eventType === "error") {
              throw new Error(parsed.message || "AI 回复失败");
            }
          } catch (parseErr) {
            if (eventType === "error" || eventType === "done") throw parseErr;
          }
        }
      }

      // 流结束但没收到 done
      set((s) => ({
        messages: s.messages.map((m) =>
          m.id === assistantMsg.id
            ? { ...m, content: fullContent || "（空回复）", isStreaming: false }
            : m
        ),
        isStreaming: false,
      }));
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : "发送消息失败";
      set((s) => ({
        error: errorMsg,
        isStreaming: false,
        messages: s.messages.map((m) =>
          m.id === assistantMsg.id
            ? { ...m, content: `❌ ${errorMsg}`, isStreaming: false }
            : m
        ),
      }));
    }
  },

  clearMessages: () => set({ messages: [], error: null }),
}));
