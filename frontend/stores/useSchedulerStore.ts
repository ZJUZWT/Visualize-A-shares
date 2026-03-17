import { create } from "zustand";
import { toast } from "sonner";
import type { ScheduledTask, CreateTaskRequest } from "@/types/scheduler";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const WS_BASE = API_BASE.replace(/^http/, "ws");

interface SchedulerStore {
  tasks: ScheduledTask[];
  loading: boolean;
  wsConnected: boolean;

  fetchTasks: () => Promise<void>;
  createTask: (req: CreateTaskRequest) => Promise<ScheduledTask | null>;
  deleteTask: (id: string) => Promise<void>;
  pauseTask: (id: string) => Promise<void>;
  resumeTask: (id: string) => Promise<void>;
  runNow: (id: string) => Promise<void>;
  connectWS: () => void;
  disconnectWS: () => void;
}

let _ws: WebSocket | null = null;
let _reconnectTimer: ReturnType<typeof setTimeout> | null = null;

export const useSchedulerStore = create<SchedulerStore>((set, get) => ({
  tasks: [],
  loading: false,
  wsConnected: false,

  fetchTasks: async () => {
    set({ loading: true });
    try {
      const res = await fetch(`${API_BASE}/api/v1/expert/tasks`);
      const data = await res.json();
      set({ tasks: Array.isArray(data) ? data : [] });
    } catch (e) {
      console.error("获取任务列表失败:", e);
    } finally {
      set({ loading: false });
    }
  },

  createTask: async (req) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/expert/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      });
      const task = await res.json();
      if (task.error) {
        toast.error(`创建失败: ${task.error}`);
        return null;
      }
      toast.success(`⏰ 定时任务「${task.name}」已创建`);
      await get().fetchTasks();
      return task;
    } catch (e) {
      toast.error("创建任务失败");
      return null;
    }
  },

  deleteTask: async (id) => {
    try {
      await fetch(`${API_BASE}/api/v1/expert/tasks/${id}`, { method: "DELETE" });
      toast.success("任务已删除");
      await get().fetchTasks();
    } catch (e) {
      toast.error("删除失败");
    }
  },

  pauseTask: async (id) => {
    try {
      await fetch(`${API_BASE}/api/v1/expert/tasks/${id}/pause`, { method: "POST" });
      toast.info("任务已暂停");
      await get().fetchTasks();
    } catch (e) {
      toast.error("暂停失败");
    }
  },

  resumeTask: async (id) => {
    try {
      await fetch(`${API_BASE}/api/v1/expert/tasks/${id}/resume`, { method: "POST" });
      toast.info("任务已恢复");
      await get().fetchTasks();
    } catch (e) {
      toast.error("恢复失败");
    }
  },

  runNow: async (id) => {
    toast.info("⏰ 正在执行任务...");
    try {
      const res = await fetch(`${API_BASE}/api/v1/expert/tasks/${id}/run`, { method: "POST" });
      const data = await res.json();
      if (data.ok) {
        toast.success("✅ 任务执行完成，可在对话中查看结果");
        await get().fetchTasks();
      } else {
        toast.error(`执行失败: ${data.error}`);
      }
    } catch (e) {
      toast.error("执行请求失败");
    }
  },

  connectWS: () => {
    if (_ws?.readyState === WebSocket.OPEN) return;

    try {
      _ws = new WebSocket(`${WS_BASE}/api/v1/expert/ws/notifications`);

      _ws.onopen = () => {
        set({ wsConnected: true });
        console.log("🔔 通知 WebSocket 已连接");
      };

      _ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "task_completed") {
            toast.success(`📊 ${msg.task_name} 执行完成`, {
              description: msg.summary?.slice(0, 80) || "点击查看详情",
              duration: 8000,
            });
            // 刷新任务列表
            get().fetchTasks();
          }
        } catch {}
      };

      _ws.onclose = () => {
        set({ wsConnected: false });
        // 5秒后自动重连
        _reconnectTimer = setTimeout(() => get().connectWS(), 5000);
      };

      _ws.onerror = () => {
        _ws?.close();
      };
    } catch (e) {
      console.error("WebSocket 连接失败:", e);
    }
  },

  disconnectWS: () => {
    if (_reconnectTimer) {
      clearTimeout(_reconnectTimer);
      _reconnectTimer = null;
    }
    if (_ws) {
      _ws.close();
      _ws = null;
    }
    set({ wsConnected: false });
  },
}));
