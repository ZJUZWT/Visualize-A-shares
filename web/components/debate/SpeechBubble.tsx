"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import type { DebateEntry } from "@/types/debate";

interface SpeechBubbleProps {
  entry: DebateEntry;
}

export default function SpeechBubble({ entry }: SpeechBubbleProps) {
  const [expanded, setExpanded] = useState(false);
  const isBull = entry.role === "bull_expert";
  const color = isBull ? "#EF4444" : "#10B981";
  const bgColor = isBull ? "bg-red-500/5" : "bg-emerald-500/5";
  const borderSide = isBull ? "border-l-2" : "border-r-2";
  const align = isBull ? "mr-auto" : "ml-auto";

  return (
    <div className={`max-w-[75%] ${align} rounded-lg p-3 ${bgColor} ${borderSide}`}
         style={{ borderColor: color }}>
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs text-[var(--text-tertiary)]">Round {entry.round}</span>
        <span className="text-xs font-medium" style={{ color }}>
          {isBull ? "多头" : "空头"}
        </span>
      </div>
      <p className="text-sm text-[var(--text-primary)] leading-relaxed">{entry.argument}</p>

      {entry.challenges.length > 0 && (
        <div className="mt-2">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
          >
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            质疑 ({entry.challenges.length})
          </button>
          {expanded && (
            <ul className="mt-1 space-y-1">
              {entry.challenges.map((c, i) => (
                <li key={i} className="text-xs text-[var(--text-secondary)] pl-2 border-l border-[var(--border)]">
                  {c}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
