"use client";

import { useSectorStore } from "@/stores/useSectorStore";

export function BoardTypeTab() {
  const { boardType, setBoardType } = useSectorStore();

  const tabs = [
    { value: "industry" as const, label: "行业板块" },
    { value: "concept" as const, label: "概念板块" },
  ];

  return (
    <div className="flex rounded-lg overflow-hidden border border-[var(--border)]">
      {tabs.map(({ value, label }) => (
        <button
          key={value}
          onClick={() => setBoardType(value)}
          className={`px-3 py-1 text-xs font-medium transition-colors
            ${boardType === value
              ? "bg-[var(--accent)] text-white"
              : "bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
