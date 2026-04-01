import type {
  ClarificationOption,
  ClarificationRequestData,
  ClarificationSelection,
} from "../types/expert.ts";

export type ClarificationSelectionMap = Map<string, ClarificationSelection>;

export function toggleClarificationOption(
  current: ClarificationSelectionMap,
  option: ClarificationOption,
  multiSelect: boolean,
): ClarificationSelectionMap {
  const next = multiSelect ? new Map(current) : new Map<string, ClarificationSelection>();
  if (current.has(option.id)) {
    next.delete(option.id);
    return next;
  }
  next.set(option.id, {
    option_id: option.id,
    label: option.label,
    title: option.title,
    focus: option.focus,
    skip: false,
  });
  return next;
}

export function toggleClarificationSubChoice(
  current: ClarificationSelectionMap,
  option: ClarificationOption,
  subChoiceId: string,
  subChoiceText: string,
  multiSelect: boolean,
): ClarificationSelectionMap {
  const next = multiSelect ? new Map(current) : new Map<string, ClarificationSelection>();
  const currentSelection = current.get(option.id);
  if (currentSelection?.sub_choice_id === subChoiceId) {
    next.delete(option.id);
    return next;
  }
  next.set(option.id, {
    option_id: option.id,
    label: option.label,
    title: option.title,
    focus: option.focus,
    skip: false,
    sub_choice_id: subChoiceId,
    sub_choice_text: subChoiceText,
  });
  return next;
}

export function buildClarificationSelections(current: ClarificationSelectionMap): ClarificationSelection[] {
  return Array.from(current.values());
}

export function shouldAutoAdvanceClarification(data: ClarificationRequestData): boolean {
  return data.should_clarify === false;
}
