"use client";

import { useEffect, useState } from "react";
import { useSchedulerStore } from "@/stores/useSchedulerStore";
import { TaskCard } from "./TaskCard";
import { CreateTaskDialog } from "./CreateTaskDialog";
import { TaskHistory } from "./TaskHistory";
import { Plus, RefreshCw, Wifi, WifiOff } from "lucide-react";

export function TaskManager() {
  const {
    tasks, loading, fetchTasks, connectWS, disconnectWS, wsConnected,
  } = useSchedulerStore();
  const [showCreate, setShowCreate] = useState(false);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);

  useEffect(() => {
    fetchTasks();
    connectWS();
    return () => disconnectWS();
  }, [fetchTasks, connectWS, disconnectWS]);

  const activeTasks = tasks.filter((t) => t.status === "active");
  const pausedTasks = tasks.filter((t) => t.status === "paused");
  const selectedTask = tasks.find((t) => t.id === selectedTaskId) ?? null;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* 顶部栏 */}
      <div className="px-6 py-3.5 border-b border-[var(--border)] shrink-0 flex items-center gap-4">
        <h1 className="text-base font-semibold text-[var(--text-primary)]">
          📋 事务管理
        </h1>
        <div className="flex items-center gap-2 text-[10px] text-[var(--text-tertiary)]">
          <span className="px-2 py-0.5 rounded-full bg-[rgba(34,197,94,0.1)] text-green-400">
            {activeTasks.length} 运行中
          </span>
          {pausedTasks.length > 0 && (
            <span className="px-2 py-0.5 rounded-full bg-[rgba(239,68,68,0.1)] text-red-400">
              {pausedTasks.length} 已暂停
            </span>
          )}
        </div>

        <div className="ml-auto flex items-center gap-2">
          {/* WS 连接状态 */}
          <div
            className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px]"
            style={{
              backgroundColor: wsConnected ? "rgba(34,197,94,0.08)" : "rgba(239,68,68,0.08)",
              color: wsConnected ? "#22C55E" : "#EF4444",
            }}
          >
            {wsConnected ? <Wifi size={10} /> : <WifiOff size={10} />}
            {wsConnected ? "实时通知已连接" : "通知未连接"}
          </div>

          <button
            onClick={() => fetchTasks()}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs
                       text-[var(--text-secondary)] hover:text-[var(--text-primary)]
                       hover:bg-[var(--bg-secondary)] transition-colors"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            刷新
          </button>

          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-medium
                       transition-colors"
            style={{ backgroundColor: "rgba(99,102,241,0.15)", color: "#818CF8" }}
          >
            <Plus size={14} />
            新建任务
          </button>
        </div>
      </div>

      {/* 主体：左侧任务列表 + 右侧任务详情/历史 */}
      <div className="flex-1 flex min-h-0">
        {/* 左侧：任务列表 */}
        <div className="w-[420px] shrink-0 border-r border-[var(--border)] flex flex-col overflow-hidden">
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {loading && tasks.length === 0 && (
              <div className="flex items-center justify-center h-40 text-sm text-[var(--text-tertiary)]">
                加载中...
              </div>
            )}
            {!loading && tasks.length === 0 && (
              <div className="flex flex-col items-center justify-center h-60 text-[var(--text-tertiary)]">
                <span className="text-3xl mb-3">📋</span>
                <p className="text-sm">暂无定时任务</p>
                <p className="text-[10px] mt-1">点击右上角「新建任务」开始</p>
              </div>
            )}
            {tasks.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                selected={task.id === selectedTaskId}
                onSelect={() => setSelectedTaskId(task.id === selectedTaskId ? null : task.id)}
              />
            ))}
          </div>
        </div>

        {/* 右侧：任务详情 + 执行历史 */}
        <div className="flex-1 min-w-0 overflow-y-auto">
          {selectedTask ? (
            <TaskHistory task={selectedTask} />
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-[var(--text-tertiary)]">
              <span className="text-4xl mb-4">👈</span>
              <p className="text-sm">选择一个任务查看详情和执行历史</p>
            </div>
          )}
        </div>
      </div>

      {/* 创建任务对话框 */}
      {showCreate && (
        <CreateTaskDialog onClose={() => setShowCreate(false)} />
      )}
    </div>
  );
}
