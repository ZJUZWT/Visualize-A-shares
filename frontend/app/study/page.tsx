"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import NavSidebar from "@/components/ui/NavSidebar";
import {
  BookOpen,
  Loader2,
  CheckCircle2,
  XCircle,
  Ban,
  Trash2,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Brain,
  Lightbulb,
  TrendingUp,
  TrendingDown,
  Minus,
} from "lucide-react";

// ─── 类型 ──────────────────────────────────────────

interface SubTask {
  code: string;
  name: string;
  status: string;
  beliefs?: number;
  error?: string;
}

interface StudyTask {
  id: string;
  target: string;
  target_type: string;
  depth: string;
  status: string;
  progress: number;
  current_step: string;
  sub_tasks: SubTask[] | string;
  result_summary: string;
  beliefs_added: number;
  error_message: string;
  created_at: string;
  completed_at: string | null;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

// ─── API ───────────────────────────────────────────

async function fetchTasks(): Promise<StudyTask[]> {
  const res = await fetch(`${API_BASE}/api/v1/study/tasks`);
  if (!res.ok) throw new Error("获取任务列表失败");
  return res.json();
}

async function createTask(target: string, depth: string): Promise<StudyTask> {
  const res = await fetch(`${API_BASE}/api/v1/study/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target, depth }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "创建任务失败");
  }
  return res.json();
}

async function cancelTask(taskId: string): Promise<void> {
  await fetch(`${API_BASE}/api/v1/study/tasks/${taskId}`, { method: "DELETE" });
}

// ─── 工具函数 ────────────────────────────────────────

function parseSubTasks(raw: SubTask[] | string): SubTask[] {
  if (Array.isArray(raw)) return raw;
  if (typeof raw === "string") {
    try { return JSON.parse(raw); } catch { return []; }
  }
  return [];
}

function relativeTime(ts: string): string {
  if (!ts) return "";
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins}分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}小时前`;
  return `${Math.floor(hours / 24)}天前`;
}

// ─── 状态图标 ────────────────────────────────────────

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "completed":
      return <CheckCircle2 size={16} className="text-emerald-500" />;
    case "running":
    case "pending":
      return <Loader2 size={16} className="text-blue-500 animate-spin" />;
    case "failed":
      return <XCircle size={16} className="text-red-500" />;
    case "cancelled":
      return <Ban size={16} className="text-gray-400" />;
    default:
      return <Loader2 size={16} className="text-gray-400" />;
  }
}

function StanceIcon({ stance }: { stance: string }) {
  if (stance?.includes("bullish") || stance?.includes("偏多"))
    return <TrendingUp size={14} className="text-red-500" />;
  if (stance?.includes("bearish") || stance?.includes("偏空"))
    return <TrendingDown size={14} className="text-green-500" />;
  return <Minus size={14} className="text-gray-400" />;
}

// ─── 输入栏 ──────────────────────────────────────────

function StudyTaskInput({
  onSubmit,
  loading,
}: {
  onSubmit: (target: string, depth: string) => void;
  loading: boolean;
}) {
  const [target, setTarget] = useState("");
  const [depth, setDepth] = useState<"quick" | "deep">("quick");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!target.trim() || loading) return;
    onSubmit(target.trim(), depth);
    setTarget("");
  };

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-3">
      <input
        type="text"
        value={target}
        onChange={(e) => setTarget(e.target.value)}
        placeholder="输入股票代码、名称或行业（如 600519 / 贵州茅台 / 半导体）"
        className="flex-1 px-4 py-2.5 rounded-xl border border-[var(--border)]
                   bg-[var(--bg-primary)] text-sm text-[var(--text-primary)]
                   placeholder:text-[var(--text-tertiary)]
                   focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30 focus:border-[var(--accent)]
                   transition-all"
      />
      <div className="flex items-center bg-[var(--bg-primary)] rounded-xl border border-[var(--border)] overflow-hidden">
        <button
          type="button"
          onClick={() => setDepth("quick")}
          className={`px-3 py-2.5 text-xs font-medium transition-colors ${
            depth === "quick"
              ? "bg-[var(--accent)] text-white"
              : "text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]"
          }`}
        >
          快速
        </button>
        <button
          type="button"
          onClick={() => setDepth("deep")}
          className={`px-3 py-2.5 text-xs font-medium transition-colors ${
            depth === "deep"
              ? "bg-[var(--accent)] text-white"
              : "text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]"
          }`}
        >
          深度
        </button>
      </div>
      <button
        type="submit"
        disabled={!target.trim() || loading}
        className="px-5 py-2.5 rounded-xl bg-[var(--accent)] text-white text-sm font-medium
                   hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed
                   transition-opacity flex items-center gap-2"
      >
        {loading ? <Loader2 size={14} className="animate-spin" /> : <BookOpen size={14} />}
        开始学习
      </button>
    </form>
  );
}

// ─── 任务卡片 ────────────────────────────────────────

function StudyTaskCard({
  task,
  onCancel,
  onRetry,
}: {
  task: StudyTask;
  onCancel: (id: string) => void;
  onRetry: (target: string, depth: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const subTasks = parseSubTasks(task.sub_tasks);
  const isRunning = task.status === "running" || task.status === "pending";

  return (
    <div
      className="rounded-xl border border-[var(--border)] bg-[var(--bg-primary)]
                 overflow-hidden transition-shadow hover:shadow-[0_2px_8px_rgba(0,0,0,0.04)]"
    >
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3">
        <StatusIcon status={task.status} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-[var(--text-primary)] truncate">
              {task.target}
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--bg-secondary)] text-[var(--text-tertiary)] font-mono">
              {task.target_type === "stock" ? "个股" : "行业"}
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--bg-secondary)] text-[var(--text-tertiary)]">
              {task.depth === "quick" ? "快速" : "深度"}
            </span>
          </div>
          {isRunning && task.current_step && (
            <p className="text-xs text-[var(--text-tertiary)] mt-0.5">
              {task.current_step}
            </p>
          )}
          {task.status === "completed" && (
            <p className="text-xs text-[var(--text-tertiary)] mt-0.5">
              {task.beliefs_added} 条信念 · {relativeTime(task.completed_at || task.created_at)}
            </p>
          )}
          {task.status === "failed" && (
            <p className="text-xs text-red-400 mt-0.5 truncate">
              {task.error_message || "未知错误"}
            </p>
          )}
        </div>

        {/* Progress bar */}
        {isRunning && (
          <div className="w-20 h-1.5 rounded-full bg-[var(--bg-secondary)] overflow-hidden">
            <div
              className="h-full rounded-full bg-[var(--accent)] transition-all duration-500"
              style={{ width: `${Math.round(task.progress * 100)}%` }}
            />
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-1">
          {isRunning && (
            <button
              onClick={() => onCancel(task.id)}
              className="p-1.5 rounded-lg text-[var(--text-tertiary)] hover:text-red-500 hover:bg-red-50 transition-colors"
              title="取消"
            >
              <Ban size={14} />
            </button>
          )}
          {task.status === "failed" && (
            <button
              onClick={() => onRetry(task.target, task.depth)}
              className="p-1.5 rounded-lg text-[var(--text-tertiary)] hover:text-[var(--accent)] hover:bg-[var(--accent-light)] transition-colors"
              title="重试"
            >
              <RefreshCw size={14} />
            </button>
          )}
          {(task.status === "completed" || subTasks.length > 0) && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="p-1.5 rounded-lg text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)] transition-colors"
            >
              {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          )}
        </div>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-[var(--border)] pt-3 space-y-3">
          {/* Result summary */}
          {task.result_summary && (
            <div className="rounded-lg bg-[var(--bg-secondary)] p-3">
              <div className="flex items-center gap-1.5 mb-1.5">
                <Lightbulb size={13} className="text-amber-500" />
                <span className="text-xs font-medium text-[var(--text-primary)]">核心发现</span>
              </div>
              <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                {task.result_summary}
              </p>
            </div>
          )}

          {/* Sub tasks for industry */}
          {subTasks.length > 0 && (
            <div>
              <span className="text-xs font-medium text-[var(--text-secondary)] mb-1.5 block">
                子任务 ({subTasks.filter((s) => s.status === "completed").length}/{subTasks.length})
              </span>
              <div className="grid grid-cols-2 gap-1.5">
                {subTasks.map((sub) => (
                  <div
                    key={sub.code}
                    className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-[var(--bg-secondary)] text-xs"
                  >
                    <StatusIcon status={sub.status} />
                    <span className="text-[var(--text-primary)] truncate">{sub.name}</span>
                    <span className="text-[var(--text-tertiary)] font-mono">{sub.code}</span>
                    {sub.beliefs !== undefined && sub.beliefs > 0 && (
                      <span className="ml-auto text-[var(--text-tertiary)]">
                        +{sub.beliefs}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── 主页面 ──────────────────────────────────────────

export default function StudyPage() {
  const [tasks, setTasks] = useState<StudyTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadTasks = useCallback(async () => {
    try {
      const data = await fetchTasks();
      setTasks(data);
    } catch {
      // 静默失败，下次轮询会重试
    }
  }, []);

  // 初始加载
  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  // 有运行中任务时轮询
  useEffect(() => {
    const hasRunning = tasks.some(
      (t) => t.status === "running" || t.status === "pending"
    );
    if (hasRunning) {
      if (!intervalRef.current) {
        intervalRef.current = setInterval(loadTasks, 3000);
      }
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [tasks, loadTasks]);

  const handleSubmit = async (target: string, depth: string) => {
    setLoading(true);
    setError("");
    try {
      await createTask(target, depth);
      await loadTasks();
    } catch (e: any) {
      setError(e.message || "创建任务失败");
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async (taskId: string) => {
    await cancelTask(taskId);
    await loadTasks();
  };

  const handleRetry = (target: string, depth: string) => {
    handleSubmit(target, depth);
  };

  return (
    <main
      className="relative h-screen bg-[var(--bg-primary)] flex flex-col"
      style={{ marginLeft: 48, width: "calc(100vw - 48px)", padding: "16px 20px 24px 20px" }}
    >
      <NavSidebar />

      {/* Header */}
      <div className="flex items-center gap-3 mb-5">
        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-purple-500 to-indigo-500 flex items-center justify-center shadow-sm">
          <Brain size={18} className="text-white" />
        </div>
        <div>
          <h1 className="text-lg font-semibold text-[var(--text-primary)]">
            Agent 学习中心
          </h1>
          <p className="text-xs text-[var(--text-tertiary)]">
            离线自学习 · 拉数据 → 多角度分析 → 沉淀知识到三层记忆
          </p>
        </div>
      </div>

      {/* Input */}
      <div className="mb-5">
        <StudyTaskInput onSubmit={handleSubmit} loading={loading} />
        {error && (
          <p className="text-xs text-red-500 mt-2 ml-1">{error}</p>
        )}
      </div>

      {/* Task list */}
      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
        {tasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-[var(--text-tertiary)]">
            <BookOpen size={36} className="mb-3 opacity-30" />
            <p className="text-sm">还没有学习任务</p>
            <p className="text-xs mt-1">输入股票代码或行业名称开始学习</p>
          </div>
        ) : (
          tasks.map((task) => (
            <StudyTaskCard
              key={task.id}
              task={task}
              onCancel={handleCancel}
              onRetry={handleRetry}
            />
          ))
        )}
      </div>
    </main>
  );
}
