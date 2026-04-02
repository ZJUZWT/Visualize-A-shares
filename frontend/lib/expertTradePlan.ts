import type { TradePlanData } from "./parseTradePlan.ts";

export type ExpertTradePlanPayload = TradePlanData & {
  source_conversation_id?: string;
};

export function buildExpertTradePlanPayload(
  plan: TradePlanData,
  sourceConversationId: string | null,
): ExpertTradePlanPayload {
  if (!sourceConversationId) {
    return plan;
  }
  return {
    ...plan,
    source_conversation_id: sourceConversationId,
  };
}
