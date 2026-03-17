"use client";

import { useEffect, useRef } from "react";
import { useExpertStore } from "@/stores/useExpertStore";
import { MessageBubble } from "./MessageBubble";

export function ChatArea() {
  const { activeExpert, profiles, chatHistories, sendMessage, status } =
    useExpertStore();
  const messages = chatHistories[activeExpert] ?? [];
  const bottomRef = useRef<HTMLDivElement>(null);
  const profile = profiles.find((p) => p.type === activeExpert);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
      {messages.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-full gap-4 select-none">
          {/* 专家图标 */}
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center text-2xl"
            style={{ backgroundColor: (profile?.color ?? "#60A5FA") + "15" }}
          >
            {profile?.icon ?? "📊"}
          </div>

          {/* 专家信息 */}
          <div className="text-center">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {profile?.name ?? "专家"}
            </p>
            <p className="text-xs text-[var(--text-tertiary)] mt-1 max-w-sm leading-relaxed">
              {profile?.description ?? ""}
            </p>
          </div>

          {/* 能力标签 */}
          <div className="flex flex-wrap gap-1.5 justify-center mt-1">
            {(profile?.description ?? "").split("、").map((tag) => (
              <span
                key={tag}
                className="px-2 py-0.5 text-[10px] rounded-md"
                style={{
                  backgroundColor: (profile?.color ?? "#60A5FA") + "15",
                  color: profile?.color ?? "#60A5FA",
                }}
              >
                {tag}
              </span>
            ))}
          </div>

          {/* 快捷建议 */}
          <div className="flex flex-wrap gap-2 justify-center mt-3 max-w-md">
            {(profile?.suggestions ?? []).map((q) => (
              <SuggestChip
                key={q}
                text={q}
                color={profile?.color ?? "#60A5FA"}
              />
            ))}
          </div>
        </div>
      ) : (
        <>
          {messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              expertColor={profile?.color ?? "#60A5FA"}
              expertIcon={profile?.icon ?? "📊"}
              expertName={profile?.name ?? "专家"}
            />
          ))}
          <div ref={bottomRef} />
        </>
      )}
    </div>
  );
}

function SuggestChip({ text, color }: { text: string; color: string }) {
  const { sendMessage, status } = useExpertStore();
  return (
    <button
      onClick={() => status === "idle" && sendMessage(text)}
      className="px-3 py-1.5 text-xs text-[var(--text-secondary)] border border-[var(--border)]
                 rounded-full hover:text-white transition-all duration-150"
      style={
        {
          "--chip-color": color,
        } as React.CSSProperties
      }
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = color;
        e.currentTarget.style.backgroundColor = color + "15";
        e.currentTarget.style.color = color;
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = "";
        e.currentTarget.style.backgroundColor = "";
        e.currentTarget.style.color = "";
      }}
    >
      {text}
    </button>
  );
}
