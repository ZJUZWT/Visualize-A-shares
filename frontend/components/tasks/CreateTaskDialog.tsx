"use client";

import { useState, useCallback } from "react";
import { useSchedulerStore } from "@/stores/useSchedulerStore";
import { CRON_PRESETS, EXPERT_OPTIONS } from "@/types/scheduler";
import type { CreateTaskRequest } from "@/types/scheduler";
import { X } from "lucide-react";

interface Props {
  onClose: () => void;
}

export function CreateTaskDialog({ onClose }: Props) {
  const { createTask } = useSchedulerStore();
  const [name, setName] = useState("");
  const [message, setMessage] = useState("");
  const [expertType, setExpertType] = useState("rag");
  const [cronExpr, setCronExpr] = useState("0 15 * * 1-5");
  const [customCron, setCustomCron] = useState("");
  const [useCustomCron, setUseCustomCron] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const effectiveCron = useCustomCron ? customCron : cronExpr;

  const handleSubmit = useCallback(async () => {
    if (!name.trim() || !message.trim() || !effectiveCron.trim()) return;
    setSubmitting(true);
    const req: CreateTaskRequest = {
      name: name.trim(),
      expert_type: expertType,
      persona: expertType === "short_term" ? "short_term" : "rag",
      message: message.trim(),
      cron_expr: effectiveCron.trim(),
      create_session: true,
    };
    const task = await createTask(req);
    setSubmitting(false);
    if (task) {
      onClose();
    }
  }, [name, message, expertType, effectiveCron, createTask, onClose]);

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center"
      style={{ backgroundColor: "rgba(0,0,0,0.6)" }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="w-[520px] rounded-2xl border shadow-2xl"
        style={{
          backgroundColor: "var(--bg-secondary)",
          borderColor: "var(--border)",
        }}
      >
        {/* 头部 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)]">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            ＋ 新建定时任务
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-[var(--bg-primary)] text-[var(--text-tertiary)]"
          >
            <X size={16} />
          </button>
        </div>

        {/* 表单 */}
        <div className="p-6 space-y-4">
          {/* 任务名称 */}
          <div>
            <label className="block text-[11px] font-medium text-[var(--text-secondary)] mb-1.5">
              任务名称
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="如：每日收盘看茅台、周一大盘分析"
              className="w-full px-3.5 py-2 text-sm rounded-lg border border-[var(--border)]
                         bg-[var(--bg-primary)] text-[var(--text-primary)]
                         placeholder:text-[var(--text-tertiary)]
                         focus:outline-none focus:border-indigo-500 transition-colors"
            />
          </div>

          {/* 分析指令 */}
          <div>
            <label className="block text-[11px] font-medium text-[var(--text-secondary)] mb-1.5">
              分析指令
            </label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="告诉 AI 你想让它分析什么，如：&#10;帮我分析贵州茅台和宁德时代的走势，给出操作建议&#10;分析今日半导体板块资金流向，判断明日走势"
              rows={3}
              className="w-full px-3.5 py-2 text-sm rounded-lg border border-[var(--border)]
                         bg-[var(--bg-primary)] text-[var(--text-primary)]
                         placeholder:text-[var(--text-tertiary)]
                         focus:outline-none focus:border-indigo-500 transition-colors resize-none"
            />
          </div>

          {/* 选择专家 */}
          <div>
            <label className="block text-[11px] font-medium text-[var(--text-secondary)] mb-1.5">
              执行专家
            </label>
            <div className="grid grid-cols-3 gap-2">
              {EXPERT_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setExpertType(opt.value)}
                  className="px-3 py-2 rounded-lg text-xs text-left transition-all"
                  style={{
                    backgroundColor:
                      expertType === opt.value
                        ? "rgba(99,102,241,0.15)"
                        : "rgba(255,255,255,0.03)",
                    border:
                      expertType === opt.value
                        ? "1px solid rgba(99,102,241,0.4)"
                        : "1px solid var(--border)",
                    color:
                      expertType === opt.value
                        ? "#818CF8"
                        : "var(--text-secondary)",
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* 执行时间 */}
          <div>
            <label className="block text-[11px] font-medium text-[var(--text-secondary)] mb-1.5">
              执行时间
            </label>
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                {CRON_PRESETS.map((p) => (
                  <button
                    key={p.value}
                    onClick={() => {
                      setCronExpr(p.value);
                      setUseCustomCron(false);
                    }}
                    className="px-3 py-2 rounded-lg text-xs text-left transition-all"
                    style={{
                      backgroundColor:
                        !useCustomCron && cronExpr === p.value
                          ? "rgba(99,102,241,0.15)"
                          : "rgba(255,255,255,0.03)",
                      border:
                        !useCustomCron && cronExpr === p.value
                          ? "1px solid rgba(99,102,241,0.4)"
                          : "1px solid var(--border)",
                      color:
                        !useCustomCron && cronExpr === p.value
                          ? "#818CF8"
                          : "var(--text-secondary)",
                    }}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setUseCustomCron(!useCustomCron)}
                  className="text-[10px] px-2 py-1 rounded transition-colors"
                  style={{
                    backgroundColor: useCustomCron
                      ? "rgba(99,102,241,0.15)"
                      : "transparent",
                    color: useCustomCron ? "#818CF8" : "var(--text-tertiary)",
                  }}
                >
                  自定义 Cron
                </button>
                {useCustomCron && (
                  <input
                    value={customCron}
                    onChange={(e) => setCustomCron(e.target.value)}
                    placeholder="如 30 9 * * 1-5（分 时 日 月 周）"
                    className="flex-1 px-3 py-1.5 text-xs rounded-lg border border-[var(--border)]
                               bg-[var(--bg-primary)] text-[var(--text-primary)]
                               placeholder:text-[var(--text-tertiary)]
                               focus:outline-none focus:border-indigo-500 font-mono"
                  />
                )}
              </div>
            </div>
          </div>
        </div>

        {/* 底部按钮 */}
        <div className="px-6 py-4 border-t border-[var(--border)] flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-xs text-[var(--text-secondary)]
                       hover:bg-[var(--bg-primary)] transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || !name.trim() || !message.trim()}
            className="px-5 py-2 rounded-lg text-xs font-medium transition-colors disabled:opacity-40"
            style={{ backgroundColor: "rgba(99,102,241,0.2)", color: "#818CF8" }}
          >
            {submitting ? "创建中..." : "创建任务"}
          </button>
        </div>
      </div>
    </div>
  );
}
