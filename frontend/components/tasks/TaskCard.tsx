"use client";

import { useSchedulerStore } from "@/stores/useSchedulerStore";
import { CRON_PRESETS, EXPERT_OPTIONS } from "@/types/scheduler";
import type { ScheduledTask } from "@/types/scheduler";
import { Play, Pause, Trash2, RotateCw } from "lucide-react";

interface Props {
  task: ScheduledTask;
  selected: boolean;
  onSelect: () => void;
}

export function TaskCard({ task, selected, onSelect }: Props) {
  const { deleteTask, pauseTask, resumeTask, runNow } = useSchedulerStore();

  const expertLabel =
    EXPERT_OPTIONS.find((e) => e.value === task.expert_type)?.label ?? task.expert_type;

  return (
    <div
      onClick={onSelect}
      className="rounded-xl p-3.5 cursor-pointer transition-all"
      style={{
        backgroundColor: selected
          ? "rgba(99,102,241,0.08)"
          : "rgba(255,255,255,0.02)",
        border: selected
          ? "1px solid rgba(99,102,241,0.3)"
          : "1px solid var(--border)",
      }}
    >
      {/* 第一行：名称 + 状态 */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-medium text-[var(--text-primary)] truncate">
            {task.name}
          </span>
          <span
            className="px-1.5 py-0.5 rounded text-[9px] font-medium shrink-0"
            style={{
              backgroundColor:
                task.status === "active"
                  ? "rgba(34,197,94,0.15)"
                  : "rgba(239,68,68,0.15)",
              color: task.status === "active" ? "#22C55E" : "#EF4444",
            }}
          >
            {task.status === "active" ? "● 运行中" : "○ 已暂停"}
          </span>
        </div>

        {/* 操作按钮 */}
        <div className="flex gap-0.5 shrink-0" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={() => runNow(task.id)}
            className="w-7 h-7 rounded-lg flex items-center justify-center
                       text-[var(--text-tertiary)] hover:text-indigo-400 hover:bg-indigo-500/10
                       transition-colors"
            title="立即执行"
          >
            <RotateCw size={12} />
          </button>
          <button
            onClick={() =>
              task.status === "active"
                ? pauseTask(task.id)
                : resumeTask(task.id)
            }
            className="w-7 h-7 rounded-lg flex items-center justify-center
                       text-[var(--text-tertiary)] hover:text-amber-400 hover:bg-amber-500/10
                       transition-colors"
            title={task.status === "active" ? "暂停" : "恢复"}
          >
            {task.status === "active" ? (
              <Pause size={12} />
            ) : (
              <Play size={12} />
            )}
          </button>
          <button
            onClick={() => {
              if (confirm(`确定删除「${task.name}」？`)) deleteTask(task.id);
            }}
            className="w-7 h-7 rounded-lg flex items-center justify-center
                       text-[var(--text-tertiary)] hover:text-red-400 hover:bg-red-500/10
                       transition-colors"
            title="删除"
          >
            <Trash2 size={12} />
          </button>
        </div>
      </div>

      {/* 第二行：指令内容 */}
      <p className="text-[11px] text-[var(--text-secondary)] mt-1.5 line-clamp-2">
        {task.message}
      </p>

      {/* 第三行：元信息 */}
      <div className="flex items-center gap-3 mt-2 text-[10px] text-[var(--text-tertiary)]">
        <span>🕐 {describeCron(task.cron_expr)}</span>
        <span>{expertLabel}</span>
      </div>

      {/* 上次执行 */}
      {task.last_run_at && (
        <div className="mt-1.5 text-[10px] text-[var(--text-tertiary)]">
          📋 上次执行：{new Date(task.last_run_at).toLocaleString("zh-CN")}
          {task.last_result_summary && (
            <span className="ml-1 text-[var(--text-secondary)]">
              — {task.last_result_summary.slice(0, 60)}
              {task.last_result_summary.length > 60 ? "..." : ""}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

/** 将 cron 表达式转为人类可读描述 */
function describeCron(expr: string): string {
  const preset = CRON_PRESETS.find((p) => p.value === expr);
  if (preset) return preset.label;

  const parts = expr.split(" ");
  if (parts.length !== 5) return expr;
  const [min, hour, , , dow] = parts;

  const days = dow === "*" ? "每天" : dow === "1-5" ? "周一至周五" : `周${dow}`;
  return `${days} ${hour}:${min.padStart(2, "0")}`;
}
