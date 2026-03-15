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

  return (
    <div className={`flex ${isBull ? "justify-start" : "justify-end"}`}>
      <div className={`max-w-[78%] rounded-xl p-4 ${bgColor} ${borderSide}`}
           style={{ borderColor: color }}>
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs text-[var(--text-tertiary)]">Round {entry.round}</span>
          <span className="text-sm font-semibold" style={{ color }}>
            {isBull ? "多头" : "空头"}
          </span>
        </div>
        <p className="text-sm text-[var(--text-primary)] leading-7">{entry.argument}</p>

        {entry.challenges.length > 0 && (
          <div className="mt-3">
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1.5 text-xs text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
            >
              {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
              质疑 ({entry.challenges.length})
            </button>
            {expanded && (
              <ul className="mt-2 space-y-2">
                {entry.challenges.map((c, i) => (
                  <li key={i} className="text-sm text-[var(--text-secondary)] pl-3 border-l-2 border-[var(--border)] leading-relaxed">
                    {c}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
