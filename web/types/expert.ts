export type ExpertEventType =
  | "thinking_start"
  | "graph_recall"
  | "tool_call"
  | "tool_result"
  | "reply_token"
  | "reply_complete"
  | "belief_updated"
  | "error";

export interface GraphNode {
  id: string;
  type: "stock" | "sector" | "event" | "belief" | "stance";
  label: string;
  confidence?: number;
}

export interface ToolCallData {
  engine: string;
  action: string;
  params: Record<string, unknown>;
}

export interface ToolResultData {
  engine: string;
  action: string;
  summary: string;
}

export interface BeliefUpdatedData {
  old: { id: string; content: string; confidence: number };
  new: { id: string; content: string; confidence: number };
  reason: string;
}

export type ThinkingItem =
  | { type: "graph_recall"; nodes: GraphNode[] }
  | { type: "tool_call"; data: ToolCallData }
  | { type: "tool_result"; data: ToolResultData }
  | { type: "belief_updated"; data: BeliefUpdatedData };

export interface ExpertMessage {
  id: string;
  role: "user" | "expert";
  content: string;
  thinking: ThinkingItem[];
  isStreaming: boolean;
}

export type ExpertStatus = "idle" | "thinking" | "error";
