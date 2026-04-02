"use client";

import { useState, useEffect, useCallback } from "react";
import NavSidebar from "@/components/ui/NavSidebar";
import TradePlanCard from "@/components/plans/TradePlanCard";
import type { TradePlanData } from "@/lib/parseTradePlan";
import { normalizeSavedTradePlanCard, type TradePlanCardSavedState } from "@/lib/planReview";
import { getApiBase, apiFetch } from "@/lib/api-base";

interface SavedPlan extends TradePlanData {
  id: string;
  status: string;
  created_at: string;
  updated_at: string;
  source_type: string;
  latest_review: TradePlanCardSavedState["latestReview"];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function normalizeSavedPlans(raw: unknown): SavedPlan[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw
    .map((item) => {
      if (!isRecord(item) || typeof item.id !== "string") {
        return null;
      }
      const savedState = normalizeSavedTradePlanCard(item);
      if (!savedState) {
        return null;
      }
      return {
        stock_code: typeof item.stock_code === "string" ? item.stock_code : "",
        stock_name: typeof item.stock_name === "string" ? item.stock_name : "",
        current_price: typeof item.current_price === "number" ? item.current_price : null,
        direction: item.direction === "sell" ? "sell" : "buy",
        entry_price: typeof item.entry_price === "string" ? item.entry_price : null,
        entry_method: typeof item.entry_method === "string" ? item.entry_method : null,
        win_odds: typeof item.win_odds === "string" ? item.win_odds : null,
        take_profit: typeof item.take_profit === "string" ? item.take_profit : null,
        take_profit_method: typeof item.take_profit_method === "string" ? item.take_profit_method : null,
        stop_loss: typeof item.stop_loss === "number" ? item.stop_loss : null,
        stop_loss_method: typeof item.stop_loss_method === "string" ? item.stop_loss_method : null,
        reasoning: typeof item.reasoning === "string" ? item.reasoning : "",
        risk_note: typeof item.risk_note === "string" ? item.risk_note : null,
        invalidation: typeof item.invalidation === "string" ? item.invalidation : null,
        valid_until: typeof item.valid_until === "string" ? item.valid_until : null,
        id: item.id,
        status: savedState.status,
        created_at: savedState.createdAt,
        updated_at: typeof item.updated_at === "string" ? item.updated_at : savedState.createdAt,
        source_type: typeof item.source_type === "string" ? item.source_type : "expert",
        latest_review: savedState.latestReview,
      } satisfies SavedPlan;
    })
    .filter((item): item is SavedPlan => item !== null);
}

const STATUS_TABS = [
  { key: "", label: "全部" },
  { key: "pending", label: "待执行" },
  { key: "executing", label: "执行中" },
  { key: "completed", label: "已完成" },
  { key: "expired", label: "已过期" },
  { key: "ignored", label: "已忽略" },
];

export default function PlansPage() {
  const [plans, setPlans] = useState<SavedPlan[]>([]);
  const [activeTab, setActiveTab] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchPlans = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (activeTab) params.set("status", activeTab);
      if (search) params.set("stock_code", search);

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 8000);

      const resp = await apiFetch(`${getApiBase()}/api/v1/agent/plans?${params}`, {
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (resp.ok) {
        setPlans(normalizeSavedPlans(await resp.json()));
      } else {
        setError(`服务端错误 (${resp.status})`);
        setPlans([]);
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setError("请求超时，请确认后端已启动");
      } else {
        setError("网络错误，请确认后端已启动");
      }
      setPlans([]);
    } finally {
      setLoading(false);
    }
  }, [activeTab, search]);

  useEffect(() => {
    fetchPlans();
  }, [fetchPlans]);

  const handleStatusChange = async (id: string, status: string) => {
    await apiFetch(`${getApiBase()}/api/v1/agent/plans/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    fetchPlans();
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除这个交易计划？")) return;
    await apiFetch(`${getApiBase()}/api/v1/agent/plans/${id}`, { method: "DELETE" });
    fetchPlans();
  };

  const handleReview = async (id: string) => {
    const resp = await apiFetch(`${getApiBase()}/api/v1/agent/plans/${id}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (!resp.ok) {
      throw new Error(`策略卡复盘失败 (${resp.status})`);
    }
    const updated = normalizeSavedTradePlanCard({
      id,
      status: "pending",
      created_at: "",
      latest_review: await resp.json(),
    });
    if (!updated) {
      throw new Error("策略卡复盘结果解析失败");
    }
    setPlans((current) =>
      current.map((plan) =>
        plan.id === id ? { ...plan, latest_review: updated.latestReview } : plan
      )
    );
    return updated.latestReview;
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
    <div className="flex h-screen bg-[#f3eadb] text-slate-950">
      <NavSidebar />
      <div className="ml-12 flex flex-1 flex-col overflow-hidden">
        {/* 顶部栏 — 与 Agent 页一致的毛玻璃风格 */}
        <div className="border-b border-black/10 bg-[#fffaf1]/90 px-5 py-4 backdrop-blur">
          <div className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Trade Plan Memo</div>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
            交易计划备忘录
          </h1>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            在专家对话中，AI 给出的交易建议可以一键收藏到这里。
          </p>

          {/* 筛选栏 */}
          <div className="mt-4 flex items-center gap-3">
            <div className="inline-flex rounded-2xl border border-black/10 bg-white/70 p-1 text-sm">
              {STATUS_TABS.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={`rounded-xl px-4 py-2 transition-colors ${
                    activeTab === tab.key
                      ? "bg-slate-950 text-white"
                      : "text-slate-600 hover:bg-black/5 hover:text-slate-950"
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
              className="rounded-xl border border-black/10 bg-white px-3 py-2 text-sm text-slate-950 placeholder-slate-400 w-48 outline-none focus:ring-2 focus:ring-slate-950/10"
            />
          </div>
        </div>

        {/* 计划列表 */}
        <div className="flex-1 overflow-y-auto p-5 space-y-3">
          {loading ? (
            <div className="text-slate-400 text-center py-20 text-sm">加载中...</div>
          ) : error ? (
            <div className="text-center py-20 space-y-3">
              <div className="text-red-500 text-sm">{error}</div>
              <button
                onClick={fetchPlans}
                className="rounded-2xl border border-black/10 bg-white px-4 py-2.5 text-sm font-medium text-slate-900 transition hover:bg-slate-50"
              >
                重试
              </button>
            </div>
          ) : displayPlans.length === 0 ? (
            <div className="flex h-full items-center justify-center">
              <div className="w-full max-w-md rounded-[28px] border border-black/10 bg-white/70 p-8 text-center shadow-[0_24px_80px_rgba(15,23,42,0.08)]">
                <div className="text-4xl mb-3">📋</div>
                <div className="text-sm text-slate-500">暂无交易计划</div>
                <div className="text-xs text-slate-400 mt-1">在专家对话中，AI 给出的交易建议可以一键收藏到这里。</div>
              </div>
            </div>
          ) : (
            displayPlans.map((plan) => (
              <TradePlanCard
                key={plan.id}
                plan={plan}
                savedPlan={{
                  id: plan.id,
                  status: plan.status,
                  createdAt: plan.created_at,
                  latestReview: plan.latest_review,
                }}
                onStatusChange={handleStatusChange}
                onDelete={handleDelete}
                onReview={handleReview}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
