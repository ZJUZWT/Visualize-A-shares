"use client";

import { useEffect, useRef } from "react";
import { Loader2 } from "lucide-react";
import type { TranscriptItem } from "@/stores/useDebateStore";
import SpeechBubble from "./SpeechBubble";

interface TranscriptFeedProps {
  transcript: TranscriptItem[];
}

export default function TranscriptFeed({ transcript }: TranscriptFeedProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcript.length]);

  if (transcript.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-[var(--text-tertiary)] text-sm">
        输入股票代码，开始辩论
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
      {transcript.map((item, idx) => {
        if (item.type === "round_divider") {
          return (
            <div key={idx} className="flex items-center gap-2 py-1">
              <div className="flex-1 h-px bg-[var(--border)]" />
              <span className="text-xs text-[var(--text-tertiary)] px-2">
                {item.is_final ? "最终轮" : `第 ${item.round} 轮`}
              </span>
              <div className="flex-1 h-px bg-[var(--border)]" />
            </div>
          );
        }
        if (item.type === "system") {
          return (
            <div key={idx} className="text-center text-xs text-[var(--text-tertiary)] py-1">
              {item.text}
            </div>
          );
        }
        if (item.type === "loading") {
          return (
            <div key={idx} className="flex items-center gap-2 text-xs text-[var(--text-tertiary)] py-1">
              <Loader2 size={12} className="animate-spin" />
              正在获取补充数据...
            </div>
          );
        }
        return <SpeechBubble key={idx} entry={item.data} />;
      })}
      <div ref={bottomRef} />
    </div>
  );
}
