import { create } from "zustand";
import type {
  ExpertMessage,
  ExpertStatus,
  ThinkingItem,
  GraphNode,
  ToolCallData,
  ToolResultData,
  BeliefUpdatedData,
} from "@/types/expert";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
let _abort: AbortController | null = null;

interface ExpertStore {
  messages: ExpertMessage[];
  status: ExpertStatus;
  error: string | null;
  sendMessage: (text: string) => Promise<void>;
  reset: () => void;
}

function newId() {
  return Math.random().toString(36).slice(2);
}

export const useExpertStore = create<ExpertStore>((set, get) => ({
  messages: [],
  status: "idle",
  error: null,

  reset: () => {
    _abort?.abort();
    _abort = null;
    set({ messages: [], status: "idle", error: null });
  },

  sendMessage: async (text: string) => {
    const userMsg: ExpertMessage = {
      id: newId(),
      role: "user",
      content: text,
      thinking: [],
      isStreaming: false,
    };
    const expertMsg: ExpertMessage = {
      id: newId(),
      role: "expert",
      content: "",
      thinking: [],
      isStreaming: true,
    };

    set((s) => ({
      messages: [...s.messages, userMsg, expertMsg],
      status: "thinking",
      error: null,
    }));

    _abort = new AbortController();

    try {
      const res = await fetch(`${API_BASE}/api/v1/expert/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
        signal: _abort.signal,
      });

      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let eventType = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";

        for (const line of lines) {
          if (line.startsWith("event:")) {
            eventType = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            const rawData = line.slice(5).trim();
            if (!rawData) continue;
            let data: Record<string, unknown>;
            try {
              data = JSON.parse(rawData);
            } catch {
              continue;
            }

            set((s) => {
              const msgs = [...s.messages];
              const idx = msgs.findIndex((m) => m.id === expertMsg.id);
              if (idx === -1) return s;
              const msg: ExpertMessage = {
                ...msgs[idx],
                thinking: [...msgs[idx].thinking],
              };

              if (eventType === "reply_token") {
                msg.content += (data.token as string) ?? "";
              } else if (eventType === "reply_complete") {
                msg.content = (data.full_text as string) ?? msg.content;
                msg.isStreaming = false;
              } else if (eventType === "graph_recall") {
                msg.thinking = [
                  ...msg.thinking,
                  { type: "graph_recall" as const, nodes: data.nodes as GraphNode[] },
                ];
              } else if (eventType === "tool_call") {
                msg.thinking = [
                  ...msg.thinking,
                  { type: "tool_call" as const, data: data as unknown as ToolCallData },
                ];
              } else if (eventType === "tool_result") {
                msg.thinking = [
                  ...msg.thinking,
                  { type: "tool_result" as const, data: data as unknown as ToolResultData },
                ];
              } else if (eventType === "belief_updated") {
                msg.thinking = [
                  ...msg.thinking,
                  { type: "belief_updated" as const, data: data as unknown as BeliefUpdatedData },
                ];
              } else if (eventType === "error") {
                msg.content = `错误: ${data.message as string}`;
                msg.isStreaming = false;
              }

              msgs[idx] = msg;
              return { messages: msgs };
            });
          }
        }
      }
    } catch (e: unknown) {
      if ((e as Error).name === "AbortError") return;
      const errMsg = (e as Error).message;
      set((s) => {
        const msgs = [...s.messages];
        const idx = msgs.findIndex((m) => m.id === expertMsg.id);
        if (idx !== -1) {
          msgs[idx] = {
            ...msgs[idx],
            content: `请求失败: ${errMsg}`,
            isStreaming: false,
          };
        }
        return { messages: msgs, status: "error", error: errMsg };
      });
    } finally {
      set(s => s.status !== "error" ? { status: "idle" } : s);
    }
  },
}));
