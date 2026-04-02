import type { ExpertType } from "../types/expert.ts";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

export interface ExpertLearningItemViewModel {
  id: string;
  title: string;
  category: string | null;
  confidence: number | null;
  verifyCount: number | null;
  date: string | null;
}

export interface ExpertLearningProfileViewModel {
  portfolioId: string | null;
  expertType: ExpertType;
  scoreCards: Array<Record<string, unknown>>;
  verifiedKnowledge: ExpertLearningItemViewModel[];
  recentLessons: ExpertLearningItemViewModel[];
  commonMistakes: ExpertLearningItemViewModel[];
  applicabilityBoundaries: ExpertLearningItemViewModel[];
  sourceSummary: {
    reviewCount: number;
    memoryCount: number;
    reflectionCount: number;
    winRate: number;
  };
  pendingPlanCount: number;
  isEmpty: boolean;
  emptyMessage: string;
}

function focusWeight(expertType: ExpertType, item: ExpertLearningItemViewModel): number {
  const category = item.category ?? "";
  const title = item.title;

  if (expertType === "data") {
    if (category.includes("data") || title.includes("成交") || title.includes("估值") || title.includes("量")) {
      return 10;
    }
  }
  if (expertType === "short_term") {
    if (category.includes("risk") || title.includes("追高") || title.includes("止损") || title.includes("短线")) {
      return 10;
    }
  }
  if (expertType === "quant") {
    if (category.includes("quant") || title.includes("信号") || title.includes("突破") || title.includes("均线")) {
      return 10;
    }
  }
  if (expertType === "info") {
    if (category.includes("info") || title.includes("消息") || title.includes("公告") || title.includes("催化")) {
      return 10;
    }
  }
  if (expertType === "industry") {
    if (category.includes("industry") || title.includes("行业") || title.includes("周期") || title.includes("产业链")) {
      return 10;
    }
  }
  return category.includes("risk") ? 4 : 1;
}

function normalizeItem(raw: unknown, index: number): ExpertLearningItemViewModel | null {
  if (!isRecord(raw)) {
    return null;
  }
  const title = typeof raw.title === "string" ? raw.title : null;
  if (!title) {
    return null;
  }
  return {
    id: typeof raw.id === "string" ? raw.id : `learning-item-${index}`,
    title,
    category: typeof raw.category === "string" ? raw.category : null,
    confidence: toNumber(raw.confidence),
    verifyCount: toNumber(raw.verify_count),
    date: typeof raw.date === "string" ? raw.date : null,
  };
}

function normalizeItems(raw: unknown): ExpertLearningItemViewModel[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw
    .map((item, index) => normalizeItem(item, index))
    .filter((item): item is ExpertLearningItemViewModel => item !== null);
}

export function normalizeExpertLearningProfile(
  raw: unknown,
  expertType: ExpertType,
): ExpertLearningProfileViewModel {
  const data = isRecord(raw) ? raw : {};
  const verifiedKnowledge = normalizeItems(data.verified_knowledge).sort((left, right) => {
    const leftWeight = focusWeight(expertType, left);
    const rightWeight = focusWeight(expertType, right);
    if (leftWeight !== rightWeight) {
      return rightWeight - leftWeight;
    }
    return (right.confidence ?? 0) - (left.confidence ?? 0);
  });

  const sourceSummary = isRecord(data.source_summary) ? data.source_summary : {};
  const reviewCount = toNumber(sourceSummary.review_count) ?? 0;
  const memoryCount = toNumber(sourceSummary.memory_count) ?? 0;
  const reflectionCount = toNumber(sourceSummary.reflection_count) ?? 0;
  const recentLessons = normalizeItems(data.recent_lessons);
  const commonMistakes = normalizeItems(data.common_mistakes);
  const applicabilityBoundaries = normalizeItems(data.applicability_boundaries);
  const isEmpty = reviewCount === 0
    && memoryCount === 0
    && reflectionCount === 0
    && recentLessons.length === 0
    && commonMistakes.length === 0
    && applicabilityBoundaries.length === 0;

  return {
    portfolioId: typeof data.portfolio_id === "string" ? data.portfolio_id : null,
    expertType,
    scoreCards: Array.isArray(data.score_cards) ? data.score_cards.filter(isRecord) : [],
    verifiedKnowledge,
    recentLessons,
    commonMistakes,
    applicabilityBoundaries,
    sourceSummary: {
      reviewCount,
      memoryCount,
      reflectionCount,
      winRate: toNumber(sourceSummary.win_rate) ?? 0,
    },
    pendingPlanCount:
      isRecord(data.pending_plan_summary) ? (toNumber(data.pending_plan_summary.expert_plan_count) ?? 0) : 0,
    isEmpty,
    emptyMessage: isEmpty ? "当前还没有足够复盘数据，等 Agent 侧产生复盘后，这里会逐渐长出来。" : "",
  };
}
