import type { TradePlanData } from "./parseTradePlan.ts";

export type ExpertTradePlanPayload = TradePlanData & {
  source_conversation_id?: string;
  source_message_id?: string;
};

export function buildExpertTradePlanPayload(
  plan: TradePlanData,
  sourceConversationId: string | null,
  sourceMessageId: string | null,
): ExpertTradePlanPayload {
  if (!sourceConversationId && !sourceMessageId) {
    return plan;
  }
  return {
    ...plan,
    ...(sourceConversationId ? { source_conversation_id: sourceConversationId } : {}),
    ...(sourceMessageId ? { source_message_id: sourceMessageId } : {}),
  };
}
