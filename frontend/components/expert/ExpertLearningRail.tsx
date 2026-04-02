"use client";

import { useEffect, useState } from "react";
import { BrainCircuit, ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";

import { apiFetch, getApiBase } from "@/lib/api-base";
import {
  ACTIVE_AGENT_PORTFOLIO_STORAGE_KEY,
  ACTIVE_AGENT_PORTFOLIO_UPDATED_EVENT,
  pickExpertLearningPortfolio,
  readRememberedAgentPortfolio,
  type PortfolioLike,
} from "@/lib/activePortfolio";
import {
  normalizeExpertLearningProfile,
  type ExpertLearningProfileViewModel,
} from "@/lib/expertLearning";
import type { ExpertProfile, ExpertType } from "@/types/expert";

interface ExpertLearningRailProps {
  expertType: ExpertType;
  profile?: ExpertProfile;
}

const EMPTY_PROFILE: ExpertLearningProfileViewModel = {
  portfolioId: null,
  expertType: "rag",
  scoreCards: [],
  verifiedKnowledge: [],
  recentLessons: [],
  commonMistakes: [],
  applicabilityBoundaries: [],
  sourceSummary: {
    reviewCount: 0,
    memoryCount: 0,
    reflectionCount: 0,
    winRate: 0,
  },
  pendingPlanCount: 0,
  isEmpty: true,
  emptyMessage: "当前还没有足够复盘数据，等 Agent 侧产生复盘后，这里会逐渐长出来。",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function normalizePortfolioList(raw: unknown): PortfolioLike[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw
    .map((item) => (isRecord(item) && typeof item.id === "string" ? { id: item.id } : null))
    .filter((item): item is PortfolioLike => item !== null);
}

function ScoreCard({
  card,
  color,
}: {
  card: Record<string, unknown>;
  color: string;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] text-[var(--text-secondary)]">
          {String(card.label ?? "")}
        </span>
        <span className="text-lg font-semibold" style={{ color }}>
          {String(card.score ?? 0)}
        </span>
      </div>
      <p className="mt-1 text-[11px] leading-5 text-[var(--text-tertiary)]">
        {String(card.summary ?? "")}
      </p>
    </div>
  );
}

function LearningSection({
  title,
  items,
  emptyText,
}: {
  title: string;
  items: ExpertLearningProfileViewModel["verifiedKnowledge"];
  emptyText: string;
}) {
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
        {title}
      </div>
      {items.length === 0 ? (
        <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">{emptyText}</p>
      ) : (
        <div className="mt-2 space-y-2">
          {items.map((item) => (
            <div key={item.id} className="rounded-xl bg-black/20 px-3 py-2">
              <div className="text-sm leading-6 text-[var(--text-primary)]">{item.title}</div>
              <div className="mt-1 flex items-center gap-2 text-[10px] text-[var(--text-tertiary)]">
                {item.category && <span>{item.category}</span>}
                {item.verifyCount !== null && <span>验证 {item.verifyCount}</span>}
                {item.date && <span>{item.date}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function ExpertLearningRail({ expertType, profile }: ExpertLearningRailProps) {
  const [expanded, setExpanded] = useState(true);
  const [portfolioId, setPortfolioId] = useState<string | null>(null);
  const [loadingPortfolio, setLoadingPortfolio] = useState(true);
  const [loadingProfile, setLoadingProfile] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [learningProfile, setLearningProfile] = useState<ExpertLearningProfileViewModel>({
    ...EMPTY_PROFILE,
    expertType,
  });
  const accentColor = profile?.color ?? "#60A5FA";

  useEffect(() => {
    let cancelled = false;

    async function resolvePortfolio() {
      setLoadingPortfolio(true);
      try {
        const resp = await apiFetch(`${getApiBase()}/api/v1/agent/portfolio`);
        if (!resp.ok) {
          throw new Error(`组合列表加载失败: ${resp.status}`);
        }
        const raw = await resp.json();
        const portfolios = normalizePortfolioList(raw);
        const nextPortfolioId = pickExpertLearningPortfolio(
          portfolios,
          readRememberedAgentPortfolio(),
          portfolioId,
        );
        if (!cancelled) {
          setPortfolioId(nextPortfolioId);
        }
      } catch (fetchError) {
        if (!cancelled) {
          setPortfolioId(null);
          setError(fetchError instanceof Error ? fetchError.message : "组合列表加载失败");
        }
      } finally {
        if (!cancelled) {
          setLoadingPortfolio(false);
        }
      }
    }

    void resolvePortfolio();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    function handlePortfolioUpdated(event: Event) {
      const customEvent = event as CustomEvent<{ portfolioId?: string | null }>;
      const nextPortfolioId =
        customEvent.detail?.portfolioId ?? readRememberedAgentPortfolio();
      setPortfolioId(nextPortfolioId ?? null);
    }

    function handleStorage(event: StorageEvent) {
      if (event.key !== ACTIVE_AGENT_PORTFOLIO_STORAGE_KEY) {
        return;
      }
      setPortfolioId(event.newValue ?? readRememberedAgentPortfolio());
    }

    window.addEventListener(ACTIVE_AGENT_PORTFOLIO_UPDATED_EVENT, handlePortfolioUpdated as EventListener);
    window.addEventListener("storage", handleStorage);
    return () => {
      window.removeEventListener(ACTIVE_AGENT_PORTFOLIO_UPDATED_EVENT, handlePortfolioUpdated as EventListener);
      window.removeEventListener("storage", handleStorage);
    };
  }, []);

  async function loadLearningProfile(targetPortfolioId: string) {
    setLoadingProfile(true);
    setError(null);
    try {
      const resp = await apiFetch(
        `${getApiBase()}/api/v1/expert/learning/profile?expert_type=${expertType}&portfolio_id=${targetPortfolioId}`,
      );
      if (!resp.ok) {
        throw new Error(`学习画像加载失败: ${resp.status}`);
      }
      const raw = await resp.json();
      setLearningProfile(normalizeExpertLearningProfile(raw, expertType));
    } catch (fetchError) {
      setLearningProfile({
        ...EMPTY_PROFILE,
        expertType,
      });
      setError(fetchError instanceof Error ? fetchError.message : "学习画像加载失败");
    } finally {
      setLoadingProfile(false);
    }
  }

  useEffect(() => {
    if (!portfolioId) {
      setLearningProfile({
        ...EMPTY_PROFILE,
        expertType,
      });
      return;
    }
    void loadLearningProfile(portfolioId);
  }, [expertType, portfolioId]);

  const loading = loadingPortfolio || loadingProfile;

  return (
    <div className="pointer-events-none fixed bottom-24 right-3 z-30 md:top-1/2 md:bottom-auto md:-translate-y-1/2">
      <div className="pointer-events-auto flex items-center justify-end gap-2">
        {expanded && (
          <div className="w-[min(360px,calc(100vw-1.5rem))] rounded-[28px] border border-white/10 bg-[var(--bg-secondary)]/95 p-4 shadow-[0_18px_60px_rgba(0,0,0,0.38)] backdrop-blur">
            <div className="flex items-start gap-3">
              <div
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl"
                style={{ backgroundColor: `${accentColor}20`, color: accentColor }}
              >
                <BrainCircuit size={18} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold text-[var(--text-primary)]">学习进度</div>
                    <div className="text-[11px] text-[var(--text-tertiary)]">
                      {profile?.name ?? "专家"} 可调用的复盘沉淀
                    </div>
                  </div>
                  <button
                    onClick={() => portfolioId && void loadLearningProfile(portfolioId)}
                    className="rounded-xl p-2 text-[var(--text-tertiary)] transition hover:bg-white/10 hover:text-[var(--text-primary)]"
                    title="刷新学习画像"
                  >
                    <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
                  </button>
                </div>
                <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-[var(--text-tertiary)]">
                  <span className="rounded-full border border-white/10 px-2 py-1">
                    账户 {learningProfile.portfolioId ?? portfolioId ?? "未选择"}
                  </span>
                  <span className="rounded-full border border-white/10 px-2 py-1">
                    复盘 {learningProfile.sourceSummary.reviewCount}
                  </span>
                  <span className="rounded-full border border-white/10 px-2 py-1">
                    规则 {learningProfile.sourceSummary.memoryCount}
                  </span>
                </div>
              </div>
            </div>

            {error && (
              <div className="mt-3 rounded-2xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-300">
                {error}
              </div>
            )}

            {loading ? (
              <div className="mt-4 rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-6 text-sm text-[var(--text-secondary)]">
                正在整理当前专家的复盘沉淀…
              </div>
            ) : learningProfile.isEmpty ? (
              <div className="mt-4 rounded-2xl border border-dashed border-white/10 bg-white/[0.03] px-4 py-6">
                <p className="text-sm leading-6 text-[var(--text-secondary)]">
                  {learningProfile.emptyMessage}
                </p>
                <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">
                  去 Agent 页跑出复盘、反思和经验规则后，这里会开始显示“已验证认知”和“常犯错误”。
                </p>
              </div>
            ) : (
              <div className="mt-4 max-h-[68vh] space-y-3 overflow-y-auto pr-1">
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {learningProfile.scoreCards.map((card, index) => (
                    <ScoreCard
                      key={String(card.id ?? index)}
                      card={card}
                      color={accentColor}
                    />
                  ))}
                </div>

                <LearningSection
                  title="已验证认知"
                  items={learningProfile.verifiedKnowledge}
                  emptyText="当前还没有足够稳定的经验规则。"
                />
                <LearningSection
                  title="最近新增复盘结论"
                  items={learningProfile.recentLessons}
                  emptyText="最近还没有新增复盘结论。"
                />
                <LearningSection
                  title="常犯错误"
                  items={learningProfile.commonMistakes}
                  emptyText="目前没有明显重复出现的错误模式。"
                />
                <LearningSection
                  title="适用边界"
                  items={learningProfile.applicabilityBoundaries}
                  emptyText="边界规则还在积累中。"
                />

                <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-3 text-xs text-[var(--text-secondary)]">
                  待验证策略卡 {learningProfile.pendingPlanCount} 张
                </div>
              </div>
            )}
          </div>
        )}

        <button
          onClick={() => setExpanded((current) => !current)}
          className="flex h-12 items-center gap-2 rounded-full border border-white/10 bg-[var(--bg-secondary)]/95 px-3 text-sm text-[var(--text-primary)] shadow-[0_12px_40px_rgba(0,0,0,0.35)] backdrop-blur transition hover:border-white/20"
        >
          <BrainCircuit size={15} style={{ color: accentColor }} />
          <span className={expanded ? "hidden md:inline" : ""}>学习进度</span>
          {expanded ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        </button>
      </div>
    </div>
  );
}
