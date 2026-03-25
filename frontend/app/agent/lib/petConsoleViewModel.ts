import type {
  AgentState,
  AgentVerificationSuiteResult,
  BrainRun,
  LedgerOverview,
  PetConsoleViewModel,
} from "../types";

interface BuildPetConsoleViewModelInput {
  activeRun: BrainRun | null;
  ledgerOverview: LedgerOverview | null;
  agentState: AgentState | null;
  strategySummary: string | null;
  suiteResult: AgentVerificationSuiteResult | null;
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

function resolvePetMood(input: BuildPetConsoleViewModelInput): PetConsoleViewModel["pet"]["mood"] {
  const suiteStatus = input.suiteResult?.overall_status ?? null;
  const activeRunStatus = input.activeRun?.status ?? null;
  const totalPnlPct = input.ledgerOverview?.account.total_pnl_pct ?? null;
  const hasBattleExposure =
    (input.ledgerOverview?.positions.length ?? 0) > 0
    || (input.ledgerOverview?.pending_plans.length ?? 0) > 0;

  if (suiteStatus) {
    return "training";
  }
  if (activeRunStatus === "running") {
    return "thinking";
  }
  if ((toNumber(totalPnlPct) ?? 0) < 0) {
    return "drawdown";
  }
  if (hasBattleExposure) {
    return "battle";
  }
  return "idle";
}

function buildPetCopy(
  mood: PetConsoleViewModel["pet"]["mood"],
  strategySummary: string | null,
): PetConsoleViewModel["pet"] {
  switch (mood) {
    case "thinking":
      return {
        mood,
        statusLabel: "思考中",
        statusMessage: "主脑正在扫描信号、权衡仓位和风险。",
      };
    case "training":
      return {
        mood,
        statusLabel: "训练中",
        statusMessage: "正在复盘和训练闭环里消化新经验。",
      };
    case "battle":
      return {
        mood,
        statusLabel: "出战中",
        statusMessage: "已经带着当前策略进入模拟战场。",
      };
    case "drawdown":
      return {
        mood,
        statusLabel: "回撤警戒",
        statusMessage: "当前处于承压阶段，需要更谨慎地收缩动作。",
      };
    default:
      return {
        mood,
        statusLabel: "待命中",
        statusMessage: strategySummary || "策略稳定，等待新的训练或出战指令。",
      };
  }
}

function summarizeTrainingSuite(
  suiteResult: AgentVerificationSuiteResult | null,
): PetConsoleViewModel["training"] {
  if (!suiteResult) {
    return {
      modeLabel: "Idle",
      statusTone: "idle",
      summary: "还没有训练结果，可以先运行 suite 或 smoke。",
    };
  }

  const summary = suiteResult.backtest?.summary as Record<string, unknown> | undefined;
  const tradeCount = toNumber(summary?.trade_count) ?? 0;
  const reviewCount = toNumber(summary?.review_count) ?? 0;
  const modeLabel = suiteResult.mode === "smoke" ? "Smoke" : "Training";

  return {
    modeLabel,
    statusTone: suiteResult.overall_status,
    summary: `${modeLabel} ${suiteResult.overall_status.toUpperCase()} · trades ${tradeCount} · reviews ${reviewCount}`,
  };
}

function summarizeBattle(
  ledgerOverview: LedgerOverview | null,
  agentState: AgentState | null,
): PetConsoleViewModel["battle"] {
  const positions = ledgerOverview?.positions.length ?? 0;
  const plans = ledgerOverview?.pending_plans.length ?? 0;
  if (positions > 0 || plans > 0) {
    return {
      readinessLabel: "已出战",
      statusMessage: `当前持仓 ${positions} 个，待执行计划 ${plans} 个。`,
    };
  }
  return {
    readinessLabel: "待出战",
    statusMessage: agentState?.position_level
      ? `当前仓位级别 ${agentState.position_level}，尚未进入战斗态。`
      : "当前没有持仓和待执行计划。",
  };
}

export function buildPetConsoleViewModel(
  input: BuildPetConsoleViewModelInput,
): PetConsoleViewModel {
  const petMood = resolvePetMood(input);
  return {
    pet: buildPetCopy(petMood, input.strategySummary),
    training: summarizeTrainingSuite(input.suiteResult),
    battle: summarizeBattle(input.ledgerOverview, input.agentState),
  };
}
