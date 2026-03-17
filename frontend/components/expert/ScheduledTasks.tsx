"use client";

import { useEffect, useState, useCallback } from "react";
import { useSchedulerStore } from "@/stores/useSchedulerStore";
import { CRON_PRESETS, EXPERT_OPTIONS } from "@/types/scheduler";
import type { CreateTaskRequest } from "@/types/scheduler";

export function ScheduledTasksPanel() {
  const { tasks, loading, fetchTasks, createTask, deleteTask, pauseTask, resumeTask, runNow, connectWS, disconnectWS, wsConnected } =
    useSchedulerStore();
  const [open, setOpen] = useState(false);
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    fetchTasks();
    connectWS();
    return () => disconnectWS();
  }, [fetchTasks, connectWS, disconnectWS]);

  return (
    <>
      {/* 触发按钮 */}
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs transition-colors"
        style={{
          backgroundColor: open ? "rgba(99,102,241,0.15)" : "rgba(99,102,241,0.08)",
          color: "#818CF8",
        }}
        title="定时任务"
      >
        <span>⏰</span>
        <span>定时任务</span>
        {tasks.length > 0 && (
          <span
            className="w-4 h-4 rounded-full text-[10px] flex items-center justify-center"
            style={{ backgroundColor: "#818CF8", color: "#fff" }}
          >
            {tasks.length}
          </span>
        )}
        <span
          className="w-1.5 h-1.5 rounded-full"
          style={{ backgroundColor: wsConnected ? "#22C55E" : "#EF4444" }}
          title={wsConnected ? "通知已连接" : "通知未连接"}
        />
      </button>

      {/* 面板 */}
      {open && (
        <div
          className="absolute right-0 top-full mt-1 z-50 w-[420px] max-h-[70vh] overflow-y-auto rounded-xl border shadow-2xl"
          style={{
            backgroundColor: "var(--bg-secondary, #1a1b2e)",
            borderColor: "var(--border, #2a2b3d)",
          }}
        >
          {/* 头部 */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-[var(--text-primary)]">⏰ 定时任务</span>
              <span className="text-[10px] text-[var(--text-tertiary)]">{tasks.length} 个任务</span>
            </div>
            <button
              onClick={() => setShowForm(!showForm)}
              className="px-2.5 py-1 text-xs rounded-lg transition-colors"
              style={{
                backgroundColor: showForm ? "rgba(239,68,68,0.15)" : "rgba(99,102,241,0.15)",
                color: showForm ? "#EF4444" : "#818CF8",
              }}
            >
              {showForm ? "✕ 取消" : "＋ 新建"}
            </button>
          </div>

          {/* 创建表单 */}
          {showForm && (
            <CreateTaskForm
              onCreated={() => setShowForm(false)}
            />
          )}

          {/* 任务列表 */}
          <div className="p-2">
            {loading && <p className="text-xs text-center py-4 text-[var(--text-tertiary)]">加载中...</p>}
            {!loading && tasks.length === 0 && (
              <p className="text-xs text-center py-6 text-[var(--text-tertiary)]">
                暂无定时任务<br />
                <span className="text-[10px]">点击「＋ 新建」创建你的第一个定时分析任务</span>
              </p>
            )}
            {tasks.map((task) => (
              <div
                key={task.id}
                className="rounded-lg p-3 mb-1.5 transition-colors"
                style={{
                  backgroundColor: "rgba(255,255,255,0.03)",
                  border: "1px solid var(--border)",
                }}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-medium text-[var(--text-primary)] truncate">
                        {task.name}
                      </span>
                      <span
                        className="px-1.5 py-0.5 rounded text-[9px]"
                        style={{
                          backgroundColor: task.status === "active" ? "rgba(34,197,94,0.15)" : "rgba(239,68,68,0.15)",
                          color: task.status === "active" ? "#22C55E" : "#EF4444",
                        }}
                      >
                        {task.status === "active" ? "运行中" : "已暂停"}
                      </span>
                    </div>
                    <p className="text-[10px] text-[var(--text-tertiary)] mt-0.5 truncate">
                      {task.message}
                    </p>
                    <div className="flex items-center gap-3 mt-1.5 text-[10px] text-[var(--text-tertiary)]">
                      <span>🕐 {describeCron(task.cron_expr)}</span>
                      <span>
                        {EXPERT_OPTIONS.find((e) => e.value === task.expert_type)?.label ?? task.expert_type}
                      </span>
                    </div>
                    {task.last_run_at && (
                      <p className="text-[10px] text-[var(--text-tertiary)] mt-1">
                        📋 上次: {new Date(task.last_run_at).toLocaleString("zh-CN")}
                        {task.last_result_summary && (
                          <span className="ml-1 text-[var(--text-secondary)]">
                            — {task.last_result_summary.slice(0, 50)}...
                          </span>
                        )}
                      </p>
                    )}
                  </div>

                  {/* 操作按钮 */}
                  <div className="flex gap-1 shrink-0">
                    <button
                      onClick={() => runNow(task.id)}
                      className="w-6 h-6 rounded flex items-center justify-center text-[10px] hover:bg-white/10"
                      title="立即执行"
                    >
                      ▶
                    </button>
                    <button
                      onClick={() => task.status === "active" ? pauseTask(task.id) : resumeTask(task.id)}
                      className="w-6 h-6 rounded flex items-center justify-center text-[10px] hover:bg-white/10"
                      title={task.status === "active" ? "暂停" : "恢复"}
                    >
                      {task.status === "active" ? "⏸" : "▶️"}
                    </button>
                    <button
                      onClick={() => { if (confirm(`确定删除「${task.name}」？`)) deleteTask(task.id); }}
                      className="w-6 h-6 rounded flex items-center justify-center text-[10px] hover:bg-red-500/20 text-red-400"
                      title="删除"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

/** 创建任务表单 */
function CreateTaskForm({ onCreated }: { onCreated: () => void }) {
  const { createTask } = useSchedulerStore();
  const [name, setName] = useState("");
  const [message, setMessage] = useState("");
  const [expertType, setExpertType] = useState("rag");
  const [cronExpr, setCronExpr] = useState("0 15 * * 1-5");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = useCallback(async () => {
    if (!name.trim() || !message.trim()) return;
    setSubmitting(true);
    const req: CreateTaskRequest = {
      name: name.trim(),
      expert_type: expertType,
      persona: expertType === "short_term" ? "short_term" : "rag",
      message: message.trim(),
      cron_expr: cronExpr,
      create_session: true,
    };
    const task = await createTask(req);
    setSubmitting(false);
    if (task) {
      setName("");
      setMessage("");
      onCreated();
    }
  }, [name, message, expertType, cronExpr, createTask, onCreated]);

  return (
    <div className="p-4 border-b border-[var(--border)]" style={{ backgroundColor: "rgba(99,102,241,0.03)" }}>
      <div className="space-y-2.5">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="任务名称，如「每日收盘看茅台」"
          className="w-full px-3 py-1.5 text-xs rounded-lg border border-[var(--border)] bg-transparent text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus:outline-none focus:border-indigo-500"
        />
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="分析指令，如「帮我分析贵州茅台和宁德时代的走势，给出操作建议」"
          rows={2}
          className="w-full px-3 py-1.5 text-xs rounded-lg border border-[var(--border)] bg-transparent text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus:outline-none focus:border-indigo-500 resize-none"
        />
        <div className="flex gap-2">
          <select
            value={expertType}
            onChange={(e) => setExpertType(e.target.value)}
            className="flex-1 px-2 py-1.5 text-xs rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] text-[var(--text-primary)] focus:outline-none"
          >
            {EXPERT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <select
            value={cronExpr}
            onChange={(e) => setCronExpr(e.target.value)}
            className="flex-1 px-2 py-1.5 text-xs rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] text-[var(--text-primary)] focus:outline-none"
          >
            {CRON_PRESETS.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </div>
        <button
          onClick={handleSubmit}
          disabled={submitting || !name.trim() || !message.trim()}
          className="w-full py-1.5 text-xs font-medium rounded-lg transition-colors disabled:opacity-40"
          style={{ backgroundColor: "rgba(99,102,241,0.2)", color: "#818CF8" }}
        >
          {submitting ? "创建中..." : "创建定时任务"}
        </button>
      </div>
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
