/**
 * 解析 AI 回复中的【交易计划】块
 */

export interface TradePlanData {
  stock_code: string;
  stock_name: string;
  current_price: number | null;
  direction: "buy" | "sell";
  entry_price: number | null;
  entry_method: string | null;
  position_pct: number | null;
  take_profit: number | null;
  take_profit_method: string | null;
  stop_loss: number | null;
  stop_loss_method: string | null;
  reasoning: string;
  risk_note: string | null;
  invalidation: string | null;
  valid_until: string | null;
}

function parseFloat2(s: string): number | null {
  const n = parseFloat(s);
  return isNaN(n) ? null : n;
}

function parseSinglePlan(block: string): TradePlanData | null {
  const lines = block.trim().split("\n");
  const raw: Record<string, string> = {};

  for (const line of lines) {
    const match = line.match(/^(.+?)：(.+)$/);
    if (match) {
      raw[match[1].trim()] = match[2].trim();
    }
  }

  // 必填字段检查
  if (!raw["标的"] || !raw["方向"] || !raw["理由"]) return null;

  // 拆分标的
  const parts = raw["标的"].split(/\s+/);
  const stock_code = parts[0] || "";
  const stock_name = parts.slice(1).join(" ") || stock_code;

  // 解析仓位百分比（"10%" → 0.1）
  let position_pct: number | null = null;
  if (raw["仓位建议"]) {
    const pctMatch = raw["仓位建议"].match(/([\d.]+)/);
    if (pctMatch) {
      position_pct = parseFloat(pctMatch[1]) / 100;
    }
  }

  return {
    stock_code,
    stock_name,
    current_price: raw["当前价格"] ? parseFloat2(raw["当前价格"]) : null,
    direction: raw["方向"] === "卖出" ? "sell" : "buy",
    entry_price: raw["建议价格"] ? parseFloat2(raw["建议价格"]) : null,
    entry_method: raw["买入方式"] || null,
    position_pct,
    take_profit: raw["止盈目标"] ? parseFloat2(raw["止盈目标"]) : null,
    take_profit_method: raw["止盈方式"] || null,
    stop_loss: raw["止损价格"] ? parseFloat2(raw["止损价格"]) : null,
    stop_loss_method: raw["止损方式"] || null,
    reasoning: raw["理由"] || "",
    risk_note: raw["风险提示"] || null,
    invalidation: raw["失效条件"] || null,
    valid_until: raw["有效期"] || null,
  };
}

/**
 * 判断文本是否包含完整的交易计划块
 */
export function hasTradePlan(text: string): boolean {
  return /【交易计划】/.test(text) && /【\/交易计划】/.test(text);
}

/**
 * 将文本按交易计划块拆分为普通文本和计划块交替的数组
 */
export function splitByTradePlan(
  text: string
): Array<{ type: "text" | "plan"; content: string; plan?: TradePlanData }> {
  const result: Array<{ type: "text" | "plan"; content: string; plan?: TradePlanData }> = [];
  const regex = /【交易计划】([\s\S]*?)【\/交易计划】/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      result.push({ type: "text", content: text.slice(lastIndex, match.index) });
    }
    const plan = parseSinglePlan(match[1]);
    result.push({
      type: "plan",
      content: match[0],
      plan: plan || undefined,
    });
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    result.push({ type: "text", content: text.slice(lastIndex) });
  }

  return result;
}
