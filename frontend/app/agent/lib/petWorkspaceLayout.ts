export interface PetWorkspaceLayout {
  rootClassName: string;
  leftColumnClassName: string;
  rightColumnClassName: string;
  leftStack: ["stage", "strategy"];
  rightStack: ["chat"];
}

export function buildPetWorkspaceLayout(): PetWorkspaceLayout {
  return {
    rootClassName: "grid min-h-full gap-5 xl:grid-cols-[minmax(0,0.98fr)_minmax(440px,1.02fr)]",
    leftColumnClassName: "flex min-h-[780px] flex-col gap-5",
    rightColumnClassName: "min-h-[780px]",
    leftStack: ["stage", "strategy"],
    rightStack: ["chat"],
  };
}
