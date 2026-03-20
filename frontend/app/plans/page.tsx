"use client";

import { useState, useEffect, useCallback } from "react";
import NavSidebar from "@/components/ui/NavSidebar";
import TradePlanCard from "@/components/plans/TradePlanCard";
import type { TradePlanData } from "@/lib/parseTradePlan";

interface SavedPlan extends TradePlanData {
  id: string;
  status: string;
  created_at: string;
  updated_at: string;
  source_type: string;
}

const STATUS_TABS = [
  { key: "", label: "全部" },
  { key: "pending", label: "待执行" },
  { key: "executing", label: "执行中" },
  { key: "completed", label: "已完成" },
  { key: "expired", label: "已过期" },
  { key: "ignored", label: "已忽略" },
];

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function PlansPage() {
  const [plans, setPlans] = useState<SavedPlan[]>([]);
  const [activeTab, setActiveTab] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  const fetchPlans = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (activeTab) params.set("status", activeTab);
      if (search) params.set("stock_code", search);
      const resp = await fetch(`${API_BASE}/api/v1/agent/plans?${params}`);
      if (resp.ok) {
        setPlans(await resp.json());
      }
    } finally {
      setLoading(false);
    }
  }, [activeTab, search]);

  useEffect(() => {
    fetchPlans();
  }, [fetchPlans]);

  const handleStatusChange = async (id: string, status: string) => {
    await fetch(`${API_BASE}/api/v1/agent/plans/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    fetchPlans();
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除这个交易计划？")) return;
    await fetch(`${API_BASE}/api/v1/agent/plans/${id}`, { method: "DELETE" });
    fetchPlans();
  };

  // 前端判断过期
  const today = new Date().toISOString().slice(0, 10);
  const displayPlans = plans.map((p) => ({
    ...p,
    status:
      p.status === "pending" && p.valid_until && p.valid_until < today
        ? "expired"
        : p.status,
  }));

  return (
    <div className="flex h-screen bg-[#0a0a0f] text-white">
      <NavSidebar />
      <div className="flex-1 flex flex-col ml-12 p-6">
        <h1 className="text-xl font-bold mb-4">📋 交易计划备忘录</h1>

        {/* 筛选栏 */}
        <div className="flex items-center gap-4 mb-4">
          <div className="flex gap-1 bg-white/5 rounded-lg p-1">
            {STATUS_TABS.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`px-3 py-1.5 rounded text-sm transition-colors ${
                  activeTab === tab.key
                    ? "bg-white/15 text-white"
                    : "text-gray-400 hover:text-white"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <input
            type="text"
            placeholder="搜索股票代码..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white placeholder-gray-500 w-48"
          />
        </div>

        {/* 计划列表 */}
        <div className="flex-1 overflow-y-auto space-y-3">
          {loading ? (
            <div className="text-gray-500 text-center py-10">加载中...</div>
          ) : displayPlans.length === 0 ? (
            <div className="text-gray-500 text-center py-10">
              暂无交易计划。在专家对话中，AI 给出的交易建议可以一键收藏到这里。
            </div>
          ) : (
            displayPlans.map((plan) => (
              <TradePlanCard
                key={plan.id}
                plan={plan}
                savedPlan={{
                  id: plan.id,
                  status: plan.status,
                  created_at: plan.created_at,
                }}
                onStatusChange={handleStatusChange}
                onDelete={handleDelete}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
