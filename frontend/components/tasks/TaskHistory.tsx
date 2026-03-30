"use client";

import { useEffect, useState } from "react";
import { CRON_PRESETS, EXPERT_OPTIONS } from "@/types/scheduler";
import type { ScheduledTask } from "@/types/scheduler";
import { useSchedulerStore } from "@/stores/useSchedulerStore";
import { Clock, Bot, MessageSquare, RotateCw } from "lucide-react";
import { getApiBase, apiFetch } from "@/lib/api-base";

interface Props {
  task: ScheduledTask;
}

interface SessionMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export function TaskHistory({ task }: Props) {
  const { runNow } = useSchedulerStore();
  const [messages, setMessages] = useState<SessionMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);

  const expertLabel =
    EXPERT_OPTIONS.find((e) => e.value === task.expert_type)?.label ?? task.expert_type;
  const cronLabel =
    CRON_PRESETS.find((p) => p.value === task.cron_expr)?.label ?? task.cron_expr;

  // 加载该任务关联 session 的消息历史
  useEffect(() => {
    if (!task.session_id) {
      setMessages([]);
      return;
    }
    setLoading(true);
    apiFetch(`${getApiBase()}/api/v1/expert/sessions/${task.session_id}/messages`)
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => setMessages(Array.isArray(data) ? data : []))
      .catch(() => setMessages([]))
      .finally(() => setLoading(false));
  }, [task.session_id, task.last_run_at]); // last_run_at 变化时也刷新

  const handleRunNow = async () => {
    setRunning(true);
    await runNow(task.id);
    setRunning(false);
  };

  return (
    <div className="flex flex-col h-full">
      {/* 任务详情头部 */}
      <div className="px-6 py-4 border-b border-[var(--border)] shrink-0">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">
              {task.name}
            </h2>
            <div className="flex items-center gap-3 mt-1.5 text-[11px] text-[var(--text-tertiary)]">
              <span className="flex items-center gap-1">
                <Clock size={10} />
                {cronLabel}
              </span>
              <span className="flex items-center gap-1">
                <Bot size={10} />
                {expertLabel}
              </span>
              <span
                className="px-1.5 py-0.5 rounded text-[9px] font-medium"
                style={{
                  backgroundColor:
                    task.status === "active"
                      ? "rgba(34,197,94,0.15)"
                      : "rgba(239,68,68,0.15)",
                  color: task.status === "active" ? "#22C55E" : "#EF4444",
                }}
              >
                {task.status === "active" ? "运行中" : "已暂停"}
              </span>
            </div>
          </div>
          <button
            onClick={handleRunNow}
            disabled={running}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-medium
                       transition-colors disabled:opacity-40"
            style={{ backgroundColor: "rgba(99,102,241,0.15)", color: "#818CF8" }}
          >
            <RotateCw size={12} className={running ? "animate-spin" : ""} />
            {running ? "执行中..." : "立即执行"}
          </button>
        </div>

        {/* 分析指令 */}
        <div className="mt-3 px-3 py-2 rounded-lg text-xs text-[var(--text-secondary)]"
          style={{ backgroundColor: "rgba(255,255,255,0.02)", border: "1px solid var(--border)" }}
        >
          <div className="flex items-center gap-1 text-[10px] text-[var(--text-tertiary)] mb-1">
            <MessageSquare size={9} />
            分析指令
          </div>
          {task.message}
        </div>

        {task.last_run_at && (
          <p className="mt-2 text-[10px] text-[var(--text-tertiary)]">
            上次执行：{new Date(task.last_run_at).toLocaleString("zh-CN")}
          </p>
        )}
      </div>

      {/* 执行历史（Session 消息） */}
      <div className="flex-1 overflow-y-auto px-6 py-4 min-h-0">
        <h3 className="text-xs font-medium text-[var(--text-secondary)] mb-3">
          执行历史 · {messages.length > 0 ? `${Math.floor(messages.length / 2)} 次执行` : "暂无"}
        </h3>

        {loading && (
          <div className="flex items-center justify-center h-20 text-xs text-[var(--text-tertiary)]">
            加载中...
          </div>
        )}

        {!loading && messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-40 text-[var(--text-tertiary)]">
            <span className="text-2xl mb-2">🕐</span>
            <p className="text-xs">该任务还没有执行过</p>
            <p className="text-[10px] mt-1">点击「立即执行」手动触发一次</p>
          </div>
        )}

        {/* 消息按对（user+assistant）分组显示 */}
        <div className="space-y-4">
          {groupMessagePairs(messages).map((pair, idx) => (
            <div
              key={idx}
              className="rounded-xl p-4 transition-colors"
              style={{
                backgroundColor: "rgba(255,255,255,0.02)",
                border: "1px solid var(--border)",
              }}
            >
              {/* 执行时间 */}
              <div className="flex items-center gap-2 text-[10px] text-[var(--text-tertiary)] mb-2">
                <span>📅 {pair.time}</span>
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-400">
                  第 {idx + 1} 次执行
                </span>
              </div>

              {/* 用户指令 */}
              {pair.user && (
                <div className="mb-2">
                  <span className="text-[9px] text-[var(--text-tertiary)]">📤 指令</span>
                  <p className="text-[11px] text-[var(--text-secondary)] mt-0.5">
                    {pair.user}
                  </p>
                </div>
              )}

              {/* AI 回复 */}
              {pair.assistant && (
                <div>
                  <span className="text-[9px] text-[var(--text-tertiary)]">🤖 回复</span>
                  <div className="text-xs text-[var(--text-primary)] mt-0.5 leading-relaxed whitespace-pre-wrap">
                    {pair.assistant}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** 将消息列表按 user+assistant 配对分组 */
function groupMessagePairs(messages: SessionMessage[]) {
  const pairs: { time: string; user: string; assistant: string }[] = [];
  let i = 0;
  while (i < messages.length) {
    const msg = messages[i];
    if (msg.role === "user") {
      const next = messages[i + 1];
      pairs.push({
        time: new Date(msg.created_at).toLocaleString("zh-CN"),
        user: msg.content,
        assistant: next?.role === "assistant" ? next.content : "",
      });
      i += next?.role === "assistant" ? 2 : 1;
    } else {
      // 孤立的 assistant 消息
      pairs.push({
        time: new Date(msg.created_at).toLocaleString("zh-CN"),
        user: "",
        assistant: msg.content,
      });
      i++;
    }
  }
  return pairs.reverse(); // 最新的在前面
}
