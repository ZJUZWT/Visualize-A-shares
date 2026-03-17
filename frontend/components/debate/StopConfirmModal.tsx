"use client";

import { useEffect } from "react";

interface StopConfirmModalProps {
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function StopConfirmModal({ open, onConfirm, onCancel }: StopConfirmModalProps) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onCancel]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-secondary)] shadow-xl px-8 py-6 w-80 space-y-4">
        <h2 className="text-base font-semibold text-[var(--text-primary)]">终止辩论？</h2>
        <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
          辩论将立即停止，并生成当前进度的中途总结。
        </p>
        <div className="flex gap-3 justify-end pt-1">
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-lg text-sm text-[var(--text-secondary)]
                       hover:bg-[var(--bg-primary)] transition-colors"
          >
            取消
          </button>
          <button
            autoFocus
            onClick={onConfirm}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-red-500 text-white
                       hover:opacity-90 transition-opacity"
          >
            确认终止
          </button>
        </div>
      </div>
    </div>
  );
}
