import { splitByTradePlan } from "@/lib/parseTradePlan";
import {
  AgentChatEntry,
  AgentStrategyActionLookup,
  AgentStrategyActionRequest,
  buildAgentStrategyKey,
} from "../types";
import AgentStrategyActionCard from "./AgentStrategyActionCard";

interface AgentChatMessageProps {
  message: AgentChatEntry;
  strategyActions: AgentStrategyActionLookup;
  onStrategyAction: (request: AgentStrategyActionRequest) => Promise<void>;
}

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--:--";
  }
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function AgentChatMessage({
  message,
  strategyActions,
  onStrategyAction,
}: AgentChatMessageProps) {
  const isUser = message.role === "user";
  const segments = isUser
    ? [{ type: "text" as const, content: message.content }]
    : splitByTradePlan(message.content);

  return (
    <article className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[92%] space-y-3 ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-2xl px-4 py-3 shadow-[0_14px_40px_rgba(0,0,0,0.18)] ${
            isUser
              ? "bg-white/10 text-white"
              : "border border-white/10 bg-[#12131b] text-gray-100"
          }`}
        >
          <div className="mb-2 flex items-center justify-between gap-3 text-[11px] uppercase tracking-[0.16em] text-gray-500">
            <span>{isUser ? "You" : "Agent"}</span>
            <span>{formatTime(message.created_at)}</span>
          </div>
          <div className="space-y-3 text-sm leading-7">
            {segments.length === 0 && message.is_streaming ? (
              <p className="whitespace-pre-wrap text-gray-300">思考中...</p>
            ) : (
              segments.map((segment, index) => {
                if (segment.type === "text") {
                  if (!segment.content.trim() && segments.length > 1) {
                    return null;
                  }
                  return (
                    <p key={`${message.id}-text-${index}`} className="whitespace-pre-wrap text-gray-200">
                      {segment.content.trim() || (message.is_streaming ? "思考中..." : "")}
                    </p>
                  );
                }

                if (!segment.plan) {
                  return (
                    <pre
                      key={`${message.id}-plan-${index}`}
                      className="overflow-x-auto rounded-xl bg-black/20 p-3 text-xs text-gray-300"
                    >
                      {segment.content}
                    </pre>
                  );
                }

                const strategyKey = buildAgentStrategyKey(segment.plan);
                return (
                  <AgentStrategyActionCard
                    key={`${message.id}-plan-${index}`}
                    messageId={message.id}
                    plan={segment.plan}
                    actionState={strategyActions[strategyKey]}
                    onAction={onStrategyAction}
                  />
                );
              })
            )}
          </div>
        </div>
      </div>
    </article>
  );
}
