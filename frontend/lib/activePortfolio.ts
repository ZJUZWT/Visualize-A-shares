export const ACTIVE_AGENT_PORTFOLIO_STORAGE_KEY = "stockscape_active_agent_portfolio";
export const ACTIVE_AGENT_PORTFOLIO_UPDATED_EVENT = "stockscape:active-agent-portfolio-updated";

export interface PortfolioLike {
  id: string;
}

export function rememberActiveAgentPortfolio(portfolioId: string | null) {
  if (typeof localStorage === "undefined") {
    return;
  }
  if (portfolioId) {
    localStorage.setItem(ACTIVE_AGENT_PORTFOLIO_STORAGE_KEY, portfolioId);
  } else {
    localStorage.removeItem(ACTIVE_AGENT_PORTFOLIO_STORAGE_KEY);
  }
  if (typeof dispatchEvent === "function") {
    const event =
      typeof CustomEvent === "function"
        ? new CustomEvent(ACTIVE_AGENT_PORTFOLIO_UPDATED_EVENT, {
            detail: { portfolioId },
          })
        : new Event(ACTIVE_AGENT_PORTFOLIO_UPDATED_EVENT);
    dispatchEvent(event);
  }
}

export function readRememberedAgentPortfolio(): string | null {
  if (typeof localStorage === "undefined") {
    return null;
  }
  return localStorage.getItem(ACTIVE_AGENT_PORTFOLIO_STORAGE_KEY);
}

export function pickExpertLearningPortfolio(
  portfolios: PortfolioLike[],
  rememberedPortfolioId: string | null,
  currentPortfolioId: string | null,
): string | null {
  if (rememberedPortfolioId && portfolios.some((portfolio) => portfolio.id === rememberedPortfolioId)) {
    return rememberedPortfolioId;
  }
  if (currentPortfolioId && portfolios.some((portfolio) => portfolio.id === currentPortfolioId)) {
    return currentPortfolioId;
  }
  return portfolios[0]?.id ?? null;
}
