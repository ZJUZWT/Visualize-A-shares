"use client";

import { X } from "lucide-react";

import type { CreatePortfolioDraft } from "../lib/portfolioWorkspace";

interface CreatePortfolioDialogProps {
  draft: CreatePortfolioDraft;
  error: string | null;
  submitting: boolean;
  onChange: (next: CreatePortfolioDraft) => void;
  onClose: () => void;
  onSubmit: () => void;
}

const MODE_OPTIONS = [
  {
    value: "paper",
    label: "虚拟盘",
    description: "默认模式，适合训练、模拟盘和回测联动。",
  },
  {
    value: "live",
    label: "Live 映射",
    description: "保留真实账户语义，但同一时间只能有一个。",
  },
] as const;

export default function CreatePortfolioDialog({
  draft,
  error,
  submitting,
  onChange,
  onClose,
  onSubmit,
}: CreatePortfolioDialogProps) {
  return (
    <div
      className="fixed inset-0 z-[120] flex items-center justify-center bg-slate-950/55 px-4"
      onClick={(event) => {
        if (event.target === event.currentTarget && !submitting) {
          onClose();
        }
      }}
    >
      <div className="w-full max-w-xl rounded-[28px] border border-black/10 bg-[#fffaf1] shadow-[0_32px_120px_rgba(15,23,42,0.28)]">
        <div className="flex items-start justify-between gap-4 border-b border-black/10 px-6 py-5">
          <div>
            <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Virtual Portfolio</p>
            <h2 className="mt-2 text-xl font-semibold text-slate-950">创建虚拟账户</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              创建后，这个宠物既能去跑虚拟盘，也能继续拿去做历史回测。
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded-full border border-black/10 p-2 text-slate-500 transition hover:bg-black/5 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="关闭创建虚拟账户弹窗"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-5 px-6 py-6">
          <div className="grid gap-5 md:grid-cols-[1.3fr,0.9fr]">
            <label className="space-y-2">
              <span className="text-xs font-medium uppercase tracking-[0.22em] text-slate-500">
                账户 ID
              </span>
              <input
                value={draft.id}
                onChange={(event) => onChange({ ...draft, id: event.target.value })}
                placeholder="如：pet-alpha"
                className="w-full rounded-2xl border border-black/10 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-400"
              />
            </label>

            <label className="space-y-2">
              <span className="text-xs font-medium uppercase tracking-[0.22em] text-slate-500">
                初始资金
              </span>
              <input
                value={draft.initialCapital}
                onChange={(event) => onChange({ ...draft, initialCapital: event.target.value })}
                placeholder="1000000"
                inputMode="decimal"
                className="w-full rounded-2xl border border-black/10 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-400"
              />
            </label>
          </div>

          <div className="space-y-2">
            <span className="text-xs font-medium uppercase tracking-[0.22em] text-slate-500">
              账户模式
            </span>
            <div className="grid gap-3 md:grid-cols-2">
              {MODE_OPTIONS.map((option) => {
                const active = draft.mode === option.value;
                return (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => onChange({ ...draft, mode: option.value })}
                    className={`rounded-[22px] border px-4 py-4 text-left transition ${
                      active
                        ? "border-slate-900 bg-slate-950 text-white"
                        : "border-black/10 bg-white text-slate-900 hover:bg-black/[0.03]"
                    }`}
                  >
                    <div className="text-sm font-semibold">{option.label}</div>
                    <div className={`mt-2 text-xs leading-5 ${active ? "text-slate-200" : "text-slate-500"}`}>
                      {option.description}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {error && (
            <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-black/10 px-6 py-5">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded-2xl border border-black/10 px-4 py-2.5 text-sm font-medium text-slate-600 transition hover:bg-black/5 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-40"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onSubmit}
            disabled={submitting}
            className="rounded-2xl bg-slate-950 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-wait disabled:opacity-50"
          >
            {submitting ? "创建中..." : "立即创建"}
          </button>
        </div>
      </div>
    </div>
  );
}
