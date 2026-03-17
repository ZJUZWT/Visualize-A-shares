"use client";

import { useSectorStore } from "@/stores/useSectorStore";

export function DatePicker() {
  const { date, setDate } = useSectorStore();

  return (
    <input
      type="date"
      value={date}
      onChange={(e) => setDate(e.target.value)}
      className="px-2 py-1 text-xs rounded-lg border border-[var(--border)]
                 bg-[var(--bg-secondary)] text-[var(--text-primary)]
                 focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
      style={{ colorScheme: "dark" }}
    />
  );
}
