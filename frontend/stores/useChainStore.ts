import { create } from "zustand";
import type { ChainNode, ChainLink, NodeShock, ExploreStatus } from "@/types/chain";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

// ── 冲击传播算法（纯前端 BFS）──
// 设计原则：
//   1. 商品价格沿产业链**同向传导**（原油涨→石脑油涨→乙烯涨→PE涨）
//   2. 企业的利好/利空由其与商品的**连边关系**决定
//      - 上游原料涨 → 成本上升 → 利空
//      - 下游产品涨 → 售价上升 → 利好
//      - 替代品涨 → 需求转移到自身 → 利好

const STRENGTH_DECAY: Record<string, number> = {
  "强刚性": 0.10,
  "中等": 0.35,
  "弱弹性": 0.60,
};

/** 商品类节点（价格沿产业链同向传导）*/
const COMMODITY_TYPES = new Set(["material", "commodity", "industry", "logistics", "macro", "event"]);

/** 企业类节点（只算利好/利空，不传播价格）*/
function isCompanyNode(nodeType: string): boolean {
  return nodeType === "company";
}

/**
 * 计算价格传导方向：
 *   上游涨 → 下游也涨（成本推升 = 同向）
 *   替代品涨 → 本品也涨（需求转移 = 同向）
 *   竞品涨 → 竞品贵了 → 本品相对便宜但不一定涨 → 中性/弱涨
 *   副产品 → 同向
 */
function getPriceDirection(
  relation: string,
  direction: "out" | "in",
): number {
  const effectiveRelation = direction === "out" ? relation : _reverseRelation(relation);
  // 所有关系的价格传导都是同向的：上游涨→下游涨，下游涨→上游也涨（需求拉动涨价）
  // substitute: A涨→B也涨（需求转移推高B价格）
  // competes: A涨→B需求增加→B也涨
  // byproduct/logistics/其他: 同向
  if (effectiveRelation === "competes") {
    return -1; // 竞品涨 → 自己相对更有优势，但价格可能不变或微跌
  }
  return 1; // 绝大多数关系价格同向传导
}

/** 转义正则特殊字符 */
function _escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * 判断企业节点与相邻商品节点的真实产业关系：是"生产商"还是"消费者"。
 *
 * LLM 标注 upstream/downstream 时经常在企业-商品之间搞混方向，
 * 所以这里用**语义推断**而非机械翻译 relation：
 *
 * 核心原则：
 *   1. 如果 link 带有 cost_input → 商品一定是企业的原料
 *   2. 如果 link 带有 byproduct → 商品一定是企业的产物
 *   3. 对于 upstream/downstream，我们统一用一个"企业是这个商品的什么角色"来判断：
 *      - 不管 LLM 标的方向，我们根据 link 两端的角色语义来判断
 *      - 企业(source) → 商品(target) + downstream = LLM 想说"企业的下游产物" → 产品
 *      - 企业(source) → 商品(target) + upstream = LLM 想说"企业的上游原料" → 原料
 *      - 商品(source) → 企业(target) + downstream = "商品流向企业" → 可能是原料输入
 *      - 商品(source) → 企业(target) + upstream = "商品的上游是企业" → 企业是生产商 → 产品
 *
 *   但实际上 LLM 经常把这些搞混！比如：
 *      - PVC → [downstream] → 中泰化学：LLM 可能想表达"中泰化学生产PVC"，
 *        但 downstream 语义变成了"中泰是PVC的下游消费者" → 利空（错！）
 *
 *   所以我们新增一个**企业-主营产品推断**：如果 impact_reason 里包含"生产""制造""产品"
 *   等关键词，就强制判定为产品关系。
 */
function getCompanyImpact(
  relation: string,
  direction: "out" | "in",
  priceSign: number,  // >0 涨, <0 跌
  impactReason?: string,  // LLM 生成的关系描述，用于辅助推断
  companyName?: string,
  commodityName?: string,
): "benefit" | "hurt" {

  // ── 第 0 步：substitute / competes 直接走简单路径 ──
  if (relation === "substitute" || relation === "competes") {
    // 替代品/竞品涨价 → 对企业有利（需求转移/竞争缓解）
    return priceSign > 0 ? "benefit" : "hurt";
  }

  // ── 第 1 步：从 impactReason 中推断真实关系 ──
  // 这是最可靠的信号：LLM 在 impactReason 里通常会用自然语言说清楚
  if (impactReason) {
    const reason = impactReason.toLowerCase();

    // ── 第 1a 步：检查明确标签（最高优先级）──
    // prompt 要求 LLM 在 impact_reason 开头用【生产】/【消费】标注角色
    if (reason.includes("【生产】") || reason.includes("[生产]")) {
      return priceSign > 0 ? "benefit" : "hurt";  // 企业是生产商 → 产品涨利好
    }
    if (reason.includes("【消费】") || reason.includes("[消费]")) {
      return priceSign > 0 ? "hurt" : "benefit";  // 企业是消费者 → 原料涨利空
    }

    // ── 第 1b 步：模式匹配推断 ──
    // "生产商""制造商""主营产品""产出""供应商" → 企业生产这个商品 → 产品
    const producerPatterns = [
      "生产", "制造", "产出", "主营", "供应商", "产能", "产量",
      "龙头", "厂商", "出产", "加工", "冶炼", "合成", "聚合",
    ];
    // "采购""消费""原料""成本""需要""使用""耗用" → 企业消费这个商品 → 原料
    const consumerPatterns = [
      "采购", "消费", "原料", "成本", "需要", "使用", "耗用",
      "进口", "购买", "投入", "输入",
    ];

    const isProducerHint = producerPatterns.some((p) => reason.includes(p));
    const isConsumerHint = consumerPatterns.some((p) => reason.includes(p));

    if (isProducerHint && !isConsumerHint) {
      // 企业是生产商 → 商品是产品 → 涨价利好
      return priceSign > 0 ? "benefit" : "hurt";
    }
    if (isConsumerHint && !isProducerHint) {
      // 企业是消费者 → 商品是原料 → 涨价利空
      return priceSign > 0 ? "hurt" : "benefit";
    }

    // ── 两者都命中时：上下文精细匹配 ──
    // 看"生产/制造"关键词附近有没有出现商品名
    // 如果 "生产PVC"/"PVC生产"/"PVC...龙头" 出现 → 企业是这个商品的生产者
    // 如果 "原料...电石"/"采购...煤炭" → 那些是其他原料，不影响对当前商品的判断
    if (isProducerHint && isConsumerHint && commodityName) {
      const commodity = commodityName.toLowerCase();

      // 策略1：商品名出现在"生产/制造/产品/产出/产能/龙头/供应"附近 → 生产商
      // 匹配模式：生产X / X生产 / X...龙头 / X产能 / 主营X / X产品
      const producerContextPatterns = [
        new RegExp(`生产.*${_escapeRegex(commodity)}`, "i"),
        new RegExp(`制造.*${_escapeRegex(commodity)}`, "i"),
        new RegExp(`${_escapeRegex(commodity)}.*生产`, "i"),
        new RegExp(`${_escapeRegex(commodity)}.*制造`, "i"),
        new RegExp(`${_escapeRegex(commodity)}.*龙头`, "i"),
        new RegExp(`${_escapeRegex(commodity)}.*产能`, "i"),
        new RegExp(`${_escapeRegex(commodity)}.*产量`, "i"),
        new RegExp(`主营.*${_escapeRegex(commodity)}`, "i"),
        new RegExp(`${_escapeRegex(commodity)}.*产品`, "i"),
        new RegExp(`核心产品.*${_escapeRegex(commodity)}`, "i"),
        new RegExp(`供应.*${_escapeRegex(commodity)}`, "i"),
      ];

      // 策略2：商品名出现在"采购/原料/成本/消费/需要"附近 → 消费者
      const consumerContextPatterns = [
        new RegExp(`采购.*${_escapeRegex(commodity)}`, "i"),
        new RegExp(`${_escapeRegex(commodity)}.*原料`, "i"),
        new RegExp(`${_escapeRegex(commodity)}.*成本`, "i"),
        new RegExp(`消费.*${_escapeRegex(commodity)}`, "i"),
        new RegExp(`需要.*${_escapeRegex(commodity)}`, "i"),
        new RegExp(`${_escapeRegex(commodity)}.*采购`, "i"),
      ];

      const isProducerContext = producerContextPatterns.some((p) => p.test(reason));
      const isConsumerContext = consumerContextPatterns.some((p) => p.test(reason));

      if (isProducerContext && !isConsumerContext) {
        return priceSign > 0 ? "benefit" : "hurt";
      }
      if (isConsumerContext && !isProducerContext) {
        return priceSign > 0 ? "hurt" : "benefit";
      }

      // 策略3：如果企业名和商品名高度相关（如"中泰化学"与"PVC"），
      // 且 reason 中出现"核心""主营""主要""最大"等词 → 大概率是生产商
      const coreProducerHints = ["核心", "主营", "主要", "最大", "龙头", "领先", "行业第"];
      if (coreProducerHints.some((h) => reason.includes(h))) {
        return priceSign > 0 ? "benefit" : "hurt";
      }
    }

    // 仍然无法判断 → fallback 到结构推断
  }

  // ── 第 2 步：结构推断（基于 relation + direction）──
  //
  // direction 是 BFS 遍历方向：
  //   "out" = 从 link.source 走到 link.target（我们正在处理 target 节点，即企业）
  //   "in"  = 从 link.target 走到 link.source（我们正在处理 source 节点，即企业）
  //
  // 所以：
  //   direction="out" → 企业是 target，商品是 source （商品→企业）
  //   direction="in"  → 企业是 source，商品是 target （企业→商品）
  //
  // LLM 标注的 relation 是从 source→target 的语义：
  //   upstream: source 是 target 的上游
  //   downstream: source 是 target 的下游
  //   cost_input: source 是 target 的成本项
  //   byproduct: source 是 target 的副产品
  let isProduct = false;

  if (relation === "cost_input") {
    // cost_input: source 是 target 的成本项
    if (direction === "out") {
      // 商品(source)是企业(target)的成本项 → 商品是企业的原料
      isProduct = false;
    } else {
      // 企业(source)是商品(target)的成本项 → 不太合理，但按原料处理
      isProduct = false;
    }
  } else if (relation === "byproduct") {
    // byproduct: source 是 target 的副产品
    if (direction === "out") {
      // 商品(source)是企业(target)的副产品 → 商品是企业的产物
      isProduct = true;
    } else {
      // 企业(source)是商品(target)的副产品 → 不合理，按产品处理
      isProduct = true;
    }
  } else if (direction === "out") {
    // 商品(source) → 企业(target)
    // relation 描述的是 source→target 的关系
    if (relation === "upstream") {
      // 商品是企业的上游 → 商品是原料，供应给企业
      isProduct = false;
    } else if (relation === "downstream") {
      // 商品是企业的下游 → 这通常是 LLM 标反的情况
      // "PVC →[downstream]→ 中泰化学" 通常意味着 LLM 想说
      // "中泰化学在 PVC 产业链的下游"（即中泰消费PVC）或者
      // "PVC 的产出方向指向中泰化学"（即中泰生产PVC）
      //
      // 由于这个方向非常模糊，且之前的 impactReason 语义推断已经失败了，
      // 我们采用保守策略：看边的另一端（商品端）的 node_type
      // 如果是 material/commodity（原材料/大宗商品）且企业名含相关行业关键词，
      // 那大概率企业是这个商品的生产商
      //
      // fallback 默认：商品→downstream→企业 = 企业是消费者
      isProduct = false;
    } else {
      isProduct = false; // 默认原料
    }
  } else {
    // direction === "in" → 企业(source) → 商品(target)
    if (relation === "downstream") {
      // 企业→[downstream]→商品 = 企业的下游是这个商品 = 企业生产商品
      isProduct = true;
    } else if (relation === "upstream") {
      // 企业→[upstream]→商品 = 企业的上游是这个商品 = 商品是原料
      isProduct = false;
    } else {
      isProduct = false;
    }
  }

  return isProduct
    ? (priceSign > 0 ? "benefit" : "hurt")   // 产品涨价→利好
    : (priceSign > 0 ? "hurt" : "benefit");   // 原料涨价→利空
}

export function propagateShocksAlgorithm(
  nodes: ChainNode[],
  links: ChainLink[],
  shocks: Map<string, NodeShock>,
): { nodes: ChainNode[]; links: ChainLink[] } {
  if (shocks.size === 0) {
    // 无冲击 → 全部回归 neutral
    return {
      nodes: nodes.map((n) => ({ ...n, impact: "neutral" as const, impact_score: 0, price_change: 0 })),
      links: links.map((l) => ({ ...l, impact: "neutral" as const })),
    };
  }

  // 节点类型查找
  const nodeTypeMap = new Map(nodes.map((n) => [n.name, n.node_type]));

  // 构建邻接表（双向）
  const adjacency = new Map<string, Array<{ neighbor: string; link: ChainLink; direction: "out" | "in" }>>();
  for (const n of nodes) {
    adjacency.set(n.name, []);
  }
  for (const l of links) {
    adjacency.get(l.source)?.push({ neighbor: l.target, link: l, direction: "out" });
    adjacency.get(l.target)?.push({ neighbor: l.source, link: l, direction: "in" });
  }

  // 存储结果：价格变动 + 利好利空
  const nodePrices = new Map<string, { totalPrice: number; count: number }>();
  const nodeImpacts = new Map<string, { totalScore: number; count: number }>();
  const linkImpacts = new Map<string, "positive" | "negative" | "neutral">();

  for (const [shockNodeName, shock] of shocks) {
    const visited = new Set<string>();
    // BFS queue: [nodeName, currentMagnitude, priceSign]
    // priceSign: +1 涨, -1 跌（沿链传导时保持/翻转）
    const queue: Array<[string, number, number]> = [
      [shockNodeName, Math.abs(shock.shock), shock.shock > 0 ? 1 : -1],
    ];
    visited.add(shockNodeName);

    while (queue.length > 0) {
      const [current, magnitude, priceSign] = queue.shift()!;
      const neighbors = adjacency.get(current) || [];

      for (const { neighbor, link, direction } of neighbors) {
        if (visited.has(neighbor) || shocks.has(neighbor)) continue;
        visited.add(neighbor);

        // 衰减
        const decayRate = STRENGTH_DECAY[link.transmission_strength] ?? 0.35;
        let newMagnitude = magnitude * (1 - decayRate);

        // dampening/amplifying 调整
        const dampeningCount = link.dampening_factors?.length || 0;
        const amplifyingCount = link.amplifying_factors?.length || 0;
        newMagnitude *= (1 - dampeningCount * 0.1) * (1 + amplifyingCount * 0.08);
        newMagnitude = Math.max(0, Math.min(1, newMagnitude));

        if (newMagnitude < 0.02) continue; // 忽略微弱影响

        const neighborType = nodeTypeMap.get(neighbor) || "industry";

        // 价格传导方向
        const priceDirMultiplier = getPriceDirection(link.relation, direction);
        const newPriceSign = priceSign * priceDirMultiplier;

        if (isCompanyNode(neighborType)) {
          // ── 企业节点：只算利好/利空，不继续传播价格 ──
          // 传入 impact_reason 帮助语义推断（解决 LLM upstream/downstream 标反问题）
          const companyName = neighbor;
          const commodityName = current;
          const impactDir = getCompanyImpact(
            link.relation, direction, priceSign,
            link.impact_reason, companyName, commodityName,
          );
          const scoreSign = impactDir === "benefit" ? 1 : -1;

          const prev = nodeImpacts.get(neighbor);
          if (prev) {
            prev.totalScore += scoreSign * newMagnitude;
            prev.count += 1;
          } else {
            nodeImpacts.set(neighbor, {
              totalScore: scoreSign * newMagnitude,
              count: 1,
            });
          }

          // 企业节点价格变动=0（企业本身没有"价格"概念）
          if (!nodePrices.has(neighbor)) {
            nodePrices.set(neighbor, { totalPrice: 0, count: 1 });
          }

          // 边着色：对企业的影响
          const linkKey = `${link.source}->${link.target}`;
          linkImpacts.set(linkKey, impactDir === "benefit" ? "positive" : "negative");

          // 企业节点不继续传播（企业是产业链末端）
        } else {
          // ── 商品/材料/行业节点：价格同向传导 ──
          const priceScore = newPriceSign * newMagnitude;

          const prevPrice = nodePrices.get(neighbor);
          if (prevPrice) {
            prevPrice.totalPrice += priceScore;
            prevPrice.count += 1;
          } else {
            nodePrices.set(neighbor, {
              totalPrice: priceScore,
              count: 1,
            });
          }

          // 商品节点的 impact 也根据价格方向设定：涨 = benefit（价格上升），跌 = hurt
          const prev = nodeImpacts.get(neighbor);
          const impactScore = newPriceSign > 0 ? newMagnitude : -newMagnitude;
          if (prev) {
            prev.totalScore += impactScore;
            prev.count += 1;
          } else {
            nodeImpacts.set(neighbor, { totalScore: impactScore, count: 1 });
          }

          // 边着色
          const linkKey = `${link.source}->${link.target}`;
          linkImpacts.set(linkKey, newPriceSign > 0 ? "positive" : "negative");

          // 继续传播（商品→商品 或 商品→企业）
          queue.push([neighbor, newMagnitude, newPriceSign]);
        }
      }
    }
  }

  // 应用结果
  const updatedNodes = nodes.map((n) => {
    if (shocks.has(n.name)) {
      const sk = shocks.get(n.name)!;
      return {
        ...n,
        impact: "source" as const,
        impact_score: sk.shock,
        price_change: sk.shock,
      };
    }
    const priceInfo = nodePrices.get(n.name);
    const impactInfo = nodeImpacts.get(n.name);

    const priceChange = priceInfo ? Math.max(-1, Math.min(1, priceInfo.totalPrice / priceInfo.count)) : 0;
    const impactAvg = impactInfo ? impactInfo.totalScore / impactInfo.count : 0;

    const impact: ChainNode["impact"] = impactAvg > 0.01 ? "benefit" : impactAvg < -0.01 ? "hurt" : "neutral";

    return {
      ...n,
      impact,
      impact_score: Math.max(-1, Math.min(1, impactAvg)),
      price_change: priceChange,
    };
  });

  const updatedLinks = links.map((l) => {
    const key = `${l.source}->${l.target}`;
    const imp = linkImpacts.get(key);
    return { ...l, impact: imp || ("neutral" as const) };
  });

  return { nodes: updatedNodes, links: updatedLinks };
}

function _reverseRelation(relation: string): string {
  if (relation === "upstream") return "downstream";
  if (relation === "downstream") return "upstream";
  return relation;
}

// ── Store ──

interface ChainStore {
  // ── 状态 ──
  nodes: ChainNode[];
  links: ChainLink[];
  status: ExploreStatus;
  subject: string;
  currentDepth: number;
  maxDepth: number;
  error: string | null;
  selectedNode: ChainNode | null;
  expandingNodes: string[];

  // ── 图谱布局设置 ──
  expandDepth: number; // 双击展开深度（1~3）
  expandDirection: "both" | "upstream" | "downstream"; // 展开方向
  expandMaxNodes: number; // 每层最多节点数，0=不限
  graphSettings: {
    linkDistance: number;   // 边长度
    nodeSize: number;       // 节点大小系数
    chargeStrength: number; // 斥力强度（负数）
  };

  // ── 沙盘模式 ──
  shocks: Map<string, NodeShock>;
  simulateSummary: string;
  simulateProgress: {
    phase: "idle" | "thinking" | "parsing" | "propagating";
    tokens: number;
    progress: number;
    nodesApplied: number;
    linksApplied: number;
  };

  // ── 操作 ──
  build: (subject: string, maxDepth?: number, focusArea?: string) => Promise<void>;
  parseAndBuild: (text: string) => Promise<void>;
  addNode: (nodeName: string, nodeType?: string) => Promise<void>;
  expandAll: () => Promise<void>;
  reindexLinks: () => Promise<void>;
  setShock: (nodeName: string, shock: number, label?: string) => void;
  clearShock: (nodeName: string) => void;
  clearAllShocks: () => void;
  simulate: () => Promise<void>;
  expandNode: (nodeName: string) => Promise<void>;
  selectNode: (node: ChainNode | null) => void;
  setMaxDepth: (depth: number) => void;
  setExpandDepth: (depth: number) => void;
  setExpandDirection: (dir: "both" | "upstream" | "downstream") => void;
  setExpandMaxNodes: (n: number) => void;
  setGraphSettings: (settings: Partial<ChainStore["graphSettings"]>) => void;
  simplifyGraph: () => { removed: number };
  reset: () => void;

  // ── 内部 ──
  _abortController: AbortController | null;
}

export const useChainStore = create<ChainStore>((set, get) => ({
  nodes: [],
  links: [],
  status: "idle",
  subject: "",
  currentDepth: 0,
  maxDepth: 1,
  error: null,
  selectedNode: null,
  expandingNodes: [],
  expandDepth: 1,
  expandDirection: "both",
  expandMaxNodes: 0,
  graphSettings: {
    linkDistance: 120,
    nodeSize: 1.0,
    chargeStrength: -300,
  },
  shocks: new Map(),
  simulateSummary: "",
  simulateProgress: {
    phase: "idle",
    tokens: 0,
    progress: 0,
    nodesApplied: 0,
    linksApplied: 0,
  },
  _abortController: null,

  // ── 构建中性网络 ──
  build: async (subject, maxDepth, focusArea) => {
    const prev = get()._abortController;
    if (prev) prev.abort();

    const controller = new AbortController();
    set({
      nodes: [],
      links: [],
      status: "building",
      subject,
      currentDepth: 0,
      maxDepth: maxDepth || get().maxDepth,
      error: null,
      selectedNode: null,
      shocks: new Map(),
      simulateSummary: "",
      _abortController: controller,
    });

    try {
      const res = await fetch(`${API_BASE}/api/v1/industry/chain/build`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subject,
          max_depth: maxDepth || get().maxDepth,
          focus_area: focusArea || "",
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        set({ status: "error", error: `HTTP ${res.status}` });
        return;
      }

      await _parseSSE(res, set, get);
    } catch (e: unknown) {
      if ((e as Error).name === "AbortError") return;
      set({ status: "error", error: (e as Error).message });
    }
  },

  // ── 智能解析 + 放置节点（统一入口 — 只放置，不扩展）──
  parseAndBuild: async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;

    const prev = get()._abortController;
    if (prev) prev.abort();
    const controller = new AbortController();

    set({
      status: "adding",
      error: null,
      _abortController: controller,
    });

    // 如果是首次，设置 subject
    if (!get().subject) {
      set({ subject: trimmed });
    }

    try {
      // 1. 调 /chain/parse 拆解文本
      const parseRes = await fetch(`${API_BASE}/api/v1/industry/chain/parse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: trimmed }),
        signal: controller.signal,
      });

      if (!parseRes.ok) {
        set({ status: get().nodes.length > 0 ? "ready" : "idle", error: `Parse HTTP ${parseRes.status}` });
        return;
      }

      const { nodes: parsedNodes } = await parseRes.json() as {
        nodes: Array<{ name: string; type: string }>;
      };

      if (!parsedNodes || parsedNodes.length === 0) {
        set({ status: get().nodes.length > 0 ? "ready" : "idle", error: "无法解析输入" });
        return;
      }

      // 逐个放置节点（轻量级：只放置 + 发现关系，不扩展上下游）
      for (const node of parsedNodes) {
        if (get().nodes.some((n) => n.name === node.name)) continue;

        set({ status: "adding" });
        const existing = get().nodes.map((n) => n.name);
        const placeRes = await fetch(`${API_BASE}/api/v1/industry/chain/place-node`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            node_name: node.name,
            node_type: node.type,
            existing_nodes: existing,
          }),
          signal: controller.signal,
        });

        if (placeRes.ok) {
          await _parseSSE(placeRes, set, get, true);
        }
      }

      // 更新 subject
      set((s) => ({
        status: "ready",
        subject: s.subject && s.subject !== trimmed
          ? `${s.subject}、${trimmed}`
          : trimmed,
      }));
    } catch (e: unknown) {
      if ((e as Error).name === "AbortError") return;
      set({ status: get().nodes.length > 0 ? "ready" : "idle", error: (e as Error).message });
    }
  },

  // ── 添加单个节点 ──
  addNode: async (nodeName, nodeType) => {
    const { nodes } = get();
    set({ status: "adding" });

    try {
      const existing = nodes.map((n) => n.name);
      const res = await fetch(`${API_BASE}/api/v1/industry/chain/add-node`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          node_name: nodeName,
          node_type: nodeType || "industry",
          existing_nodes: existing,
        }),
      });

      if (!res.ok) {
        set({ status: "ready", error: `HTTP ${res.status}` });
        return;
      }

      await _parseSSE(res, set, get, true);
      set({ status: "ready" });
    } catch (e: unknown) {
      set({ status: "ready", error: (e as Error).message });
    }
  },

  // ── 全局扩展 ──
  expandAll: async () => {
    const { nodes, links } = get();

    // 统计出度和入度
    const outDegree = new Map<string, number>();
    const inDegree = new Map<string, number>();
    for (const l of links) {
      outDegree.set(l.source, (outDegree.get(l.source) || 0) + 1);
      inDegree.set(l.target, (inDegree.get(l.target) || 0) + 1);
    }

    // 稀疏度阈值：入度或出度 ≤ SPARSE 视为信息不足，需要补充扩展
    // 例如 PVC 只有一条 电石→PVC 的入边 → 入度稀疏 → 补充上游（乙烯法等替代路线）
    const SPARSE = 1;

    // 智能分类：按稀疏度决定每个节点的扩展方向
    const targets: Array<{ name: string; direction: string }> = [];
    for (const n of nodes) {
      const out = outDegree.get(n.name) || 0;
      const inp = inDegree.get(n.name) || 0;

      const sparseIn = inp <= SPARSE;   // 上游来源不足
      const sparseOut = out <= SPARSE;  // 下游去向不足

      if (sparseIn && sparseOut) {
        // 两个方向都稀疏 → 全方位扩展
        targets.push({ name: n.name, direction: "both" });
      } else if (sparseOut) {
        // 下游稀疏 → 补充下游
        targets.push({ name: n.name, direction: "downstream" });
      } else if (sparseIn) {
        // 上游稀疏 → 补充上游（发现更多制备路线、原料来源）
        targets.push({ name: n.name, direction: "upstream" });
      }
      // 两个方向都 >= 2 → 信息足够丰富，不扩展
    }

    if (targets.length === 0) return;

    const allNodeNames = nodes.map((n) => n.name);
    const targetNames = targets.map((t) => t.name);
    set({ status: "building", expandingNodes: targetNames });

    try {
      const depth = get().expandDepth;
      const res = await fetch(`${API_BASE}/api/v1/industry/chain/expand-all`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          targets,
          existing_nodes: allNodeNames,
          max_depth: depth,
        }),
      });

      if (!res.ok) {
        set({ status: "ready", expandingNodes: [], error: `HTTP ${res.status}` });
        return;
      }

      await _parseSSE(res, set, get, true);
      set({ status: "ready", expandingNodes: [] });
    } catch (e: unknown) {
      set({ status: "ready", expandingNodes: [], error: (e as Error).message });
    }
  },

  // ── 重整关系 ──
  reindexLinks: async () => {
    const { nodes, links } = get();
    if (nodes.length < 2) return;

    set({ status: "building" });

    try {
      const res = await fetch(`${API_BASE}/api/v1/industry/chain/reindex-links`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nodes: nodes.map((n) => ({ name: n.name, node_type: n.node_type })),
          links: links.map((l) => ({
            source: l.source,
            target: l.target,
            relation: l.relation,
          })),
        }),
      });

      if (!res.ok) {
        set({ status: "ready", error: `HTTP ${res.status}` });
        return;
      }

      await _parseSSE(res, set, get, true);
      set({ status: "ready" });
    } catch (e: unknown) {
      set({ status: "ready", error: (e as Error).message });
    }
  },

  // ── 施加 / 清除冲击 — 自动触发纯前端传播 ──
  setShock: (nodeName, shock, label) => {
    set((s) => {
      const next = new Map(s.shocks);
      next.set(nodeName, { node_name: nodeName, shock, shock_label: label || "" });
      const { nodes: propagated, links: propagatedLinks } = propagateShocksAlgorithm(
        s.nodes, s.links, next,
      );
      return { shocks: next, nodes: propagated, links: propagatedLinks };
    });
  },

  clearShock: (nodeName) => {
    set((s) => {
      const next = new Map(s.shocks);
      next.delete(nodeName);
      const { nodes: propagated, links: propagatedLinks } = propagateShocksAlgorithm(
        s.nodes, s.links, next,
      );
      return { shocks: next, nodes: propagated, links: propagatedLinks };
    });
  },

  clearAllShocks: () => {
    set((s) => ({
      shocks: new Map(),
      simulateSummary: "",
      simulateProgress: { phase: "idle", tokens: 0, progress: 0, nodesApplied: 0, linksApplied: 0 },
      nodes: s.nodes.map((n) => ({
        ...n,
        impact: "neutral" as const,
        impact_score: 0,
        price_change: 0,
      })),
      links: s.links.map((l) => ({ ...l, impact: "neutral" as const })),
    }));
  },

  // ── AI 深度解读（原 simulate）──
  simulate: async () => {
    const { shocks, subject, nodes, links } = get();
    if (shocks.size === 0) return;

    set({ status: "simulating", error: null, simulateProgress: {
      phase: "thinking",
      tokens: 0,
      progress: 0,
      nodesApplied: 0,
      linksApplied: 0,
    }});

    const nodesForApi = nodes.map((n) => ({
      name: n.name,
      node_type: n.node_type,
      summary: n.summary,
      constraint_summary: n.constraint
        ? [
            n.constraint.shutdown_recovery_time,
            n.constraint.capacity_ceiling,
            n.constraint.inventory_buffer_days,
            n.constraint.import_dependency,
            n.constraint.substitution_path,
          ].filter(Boolean).join("; ")
        : "",
    }));

    const linksForApi = links.map((l) => ({
      source: l.source,
      target: l.target,
      relation: l.relation,
      transmission_speed: l.transmission_speed,
      transmission_strength: l.transmission_strength,
      transmission_mechanism: l.transmission_mechanism,
    }));

    try {
      const res = await fetch(`${API_BASE}/api/v1/industry/chain/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subject,
          shocks: Array.from(shocks.values()),
          nodes: nodesForApi,
          links: linksForApi,
        }),
      });

      if (!res.ok) {
        set({ status: "ready", error: `HTTP ${res.status}` });
        return;
      }

      await _parseSimulateSSE(res, set, get);
    } catch (e: unknown) {
      set({ status: "ready", error: (e as Error).message });
    }
  },

  // ── 展开节点（双击触发）— 使用 expandDepth ──
  // 优化版：阶段1 build + 阶段2 批量relate（1次LLM调用代替N次串行add-node）
  expandNode: async (nodeName) => {
    const { subject, expandingNodes, expandDepth, expandDirection, expandMaxNodes, nodes } = get();
    if (!subject || expandingNodes.includes(nodeName)) return;

    set({ expandingNodes: [...expandingNodes, nodeName] });

    try {
      const existingNames = nodes.map((n) => n.name);

      // ── 阶段 1：build(subject=nodeName, depth=expandDepth, direction, maxNodes) ──
      const buildBody: Record<string, unknown> = {
        subject: nodeName,
        max_depth: expandDepth,
        expand_direction: expandDirection,
      };
      if (expandMaxNodes > 0) {
        buildBody.max_nodes = expandMaxNodes;
      }

      const res = await fetch(`${API_BASE}/api/v1/industry/chain/build`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildBody),
      });

      if (!res.ok) {
        set((s) => ({
          expandingNodes: s.expandingNodes.filter((n) => n !== nodeName),
        }));
        return;
      }

      await _parseSSE(res, set, get, true);

      // ── 阶段 2：批量 relate — 一次 LLM 调用发现所有新节点与旧图的关系 ──
      const newNodes = get().nodes.filter((n) => !existingNames.includes(n.name));
      if (newNodes.length > 0 && existingNames.length > 0) {
        try {
          const relateRes = await fetch(`${API_BASE}/api/v1/industry/chain/relate-batch`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              new_nodes: newNodes.slice(0, 15).map((n) => ({
                name: n.name,
                node_type: n.node_type,
              })),
              existing_nodes: existingNames,
            }),
          });
          if (relateRes.ok) {
            await _parseSSE(relateRes, set, get, true);
          }
        } catch {
          // relate 失败不影响展开结果
        }
      }

      set((s) => ({
        expandingNodes: s.expandingNodes.filter((n) => n !== nodeName),
      }));
    } catch {
      set((s) => ({
        expandingNodes: s.expandingNodes.filter((n) => n !== nodeName),
      }));
    }
  },

  selectNode: (node) => set({ selectedNode: node }),
  setMaxDepth: (depth) => set({ maxDepth: depth }),
  setExpandDepth: (depth) => set({ expandDepth: Math.max(1, Math.min(3, depth)) }),
  setExpandDirection: (dir) => set({ expandDirection: dir }),
  setExpandMaxNodes: (n) => set({ expandMaxNodes: Math.max(0, Math.min(20, n)) }),
  setGraphSettings: (settings) => set((s) => ({
    graphSettings: { ...s.graphSettings, ...settings },
  })),

  // ── 精简图谱：传递性归约（Transitive Reduction）──
  // 如果 A→B→C 存在，则 A→C 是冗余的（信息已通过 B 间接传达），可以删除
  // 只对方向性传导边做归约（upstream/downstream/cost_input），不动 substitute/competes/byproduct 等
  simplifyGraph: () => {
    const { nodes, links } = get();
    if (links.length === 0) return { removed: 0 };

    // 可归约的边类型：方向性传导关系（A是B的上游/下游/成本项 → 有传递性）
    const TRANSITIVE_RELATIONS = new Set([
      "upstream", "downstream", "cost_input",
    ]);

    // 构建邻接表：node → Set<直接后继 node>（只考虑可归约类型的边）
    const adj = new Map<string, Set<string>>();
    const allNodes = new Set(nodes.map((n) => n.name));

    for (const link of links) {
      if (!TRANSITIVE_RELATIONS.has(link.relation)) continue;
      if (!allNodes.has(link.source) || !allNodes.has(link.target)) continue;
      if (!adj.has(link.source)) adj.set(link.source, new Set());
      adj.get(link.source)!.add(link.target);
    }

    // 对每条可归约的边 A→C，检查是否存在中间节点 B 使得 A→B 且 B 能到达 C（BFS，深度≤3）
    const redundant = new Set<string>(); // "source->target" keys

    for (const link of links) {
      if (!TRANSITIVE_RELATIONS.has(link.relation)) continue;
      const { source, target } = link;
      const neighbors = adj.get(source);
      if (!neighbors || neighbors.size <= 1) continue;

      // 从 source 的每个邻居 B（B≠target）出发，BFS 看能否在短路径内到达 target
      for (const mid of neighbors) {
        if (mid === target) continue;
        // BFS from mid, max depth 2 (so total path A→B→...→C is max 3 hops)
        const visited = new Set<string>([source, mid]);
        let frontier = [mid];
        let found = false;
        for (let d = 0; d < 2 && !found; d++) {
          const next: string[] = [];
          for (const cur of frontier) {
            const curAdj = adj.get(cur);
            if (!curAdj) continue;
            for (const nb of curAdj) {
              if (nb === target) { found = true; break; }
              if (!visited.has(nb)) {
                visited.add(nb);
                next.push(nb);
              }
            }
            if (found) break;
          }
          frontier = next;
        }
        if (found) {
          redundant.add(`${source}->${target}`);
          break;
        }
      }
    }

    if (redundant.size === 0) return { removed: 0 };

    // 过滤掉冗余边
    set((s) => ({
      links: s.links.filter((l) => !redundant.has(`${l.source}->${l.target}`)),
    }));

    return { removed: redundant.size };
  },

  reset: () => {
    const prev = get()._abortController;
    if (prev) prev.abort();
    set({
      nodes: [],
      links: [],
      status: "idle",
      subject: "",
      currentDepth: 0,
      error: null,
      selectedNode: null,
      expandingNodes: [],
      shocks: new Map(),
      simulateSummary: "",
      simulateProgress: { phase: "idle", tokens: 0, progress: 0, nodesApplied: 0, linksApplied: 0 },
      _abortController: null,
    });
  },
}));


// ── SSE 解析 — build 流 ──

async function _parseSSE(
  res: Response,
  set: (partial: Partial<ChainStore> | ((s: ChainStore) => Partial<ChainStore>)) => void,
  get: () => ChainStore,
  isExpand = false,
) {
  const reader = res.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const events = buffer.split("\n\n");
    buffer = events.pop() || "";

    for (const eventBlock of events) {
      const lines = eventBlock.split("\n");
      let eventType = "";
      let eventData = "";
      for (const line of lines) {
        if (line.startsWith("event: ")) eventType = line.slice(7).trim();
        if (line.startsWith("data: ")) eventData = line.slice(6).trim();
      }
      if (!eventType || !eventData) continue;

      try {
        const parsed = JSON.parse(eventData);

        switch (eventType) {
          case "depth_start":
            set({ currentDepth: parsed.depth || 0 });
            break;

          case "nodes_discovered": {
            const newNodes: ChainNode[] = (parsed.nodes || []).map((n: ChainNode) => ({
              ...n,
              id: n.id || `n_${n.name}`,
              price_change: n.price_change ?? 0,
            }));
            set((s) => {
              const existingNames = new Set(s.nodes.map((n) => n.name));
              const unique = newNodes.filter((n) => !existingNames.has(n.name));
              return { nodes: [...s.nodes, ...unique] };
            });
            break;
          }

          case "links_discovered": {
            const newLinks: ChainLink[] = parsed.links || [];
            set((s) => {
              const existingKeys = new Set(s.links.map((l) => `${l.source}->${l.target}`));
              const unique = newLinks.filter((l) => !existingKeys.has(`${l.source}->${l.target}`));
              return { links: [...s.links, ...unique] };
            });
            break;
          }

          case "nodes_removed": {
            const removeNames: string[] = parsed.nodes || [];
            if (removeNames.length > 0) {
              set((s) => ({
                nodes: s.nodes.filter((n) => !removeNames.includes(n.name)),
              }));
            }
            break;
          }

          case "build_complete":
          case "explore_complete":
          case "add_node_complete":
          case "place_node_complete":
          case "expand_all_complete":
          case "relate_batch_complete":
          case "reindex_complete":
            if (!isExpand) {
              set({ status: "ready" });
            }
            break;

          case "reindex_start":
            // 进度提示（可选）
            break;

          case "error":
            set({ error: parsed.message || "未知错误" });
            break;
        }
      } catch {
        // skip
      }
    }
  }
}


// ── SSE 解析 — simulate 流 ──

async function _parseSimulateSSE(
  res: Response,
  set: (partial: Partial<ChainStore> | ((s: ChainStore) => Partial<ChainStore>)) => void,
  get: () => ChainStore,
) {
  const reader = res.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = "";
  let nodesApplied = 0;
  let linksApplied = 0;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const events = buffer.split("\n\n");
    buffer = events.pop() || "";

    for (const eventBlock of events) {
      const lines = eventBlock.split("\n");
      let eventType = "";
      let eventData = "";
      for (const line of lines) {
        if (line.startsWith("event: ")) eventType = line.slice(7).trim();
        if (line.startsWith("data: ")) eventData = line.slice(6).trim();
      }
      if (!eventType || !eventData) continue;

      try {
        const parsed = JSON.parse(eventData);

        switch (eventType) {
          case "simulate_thinking": {
            set((s) => ({
              simulateProgress: {
                ...s.simulateProgress,
                phase: parsed.phase || "thinking",
                tokens: parsed.tokens || 0,
                progress: parsed.progress || 0,
              },
            }));
            break;
          }

          case "node_impact": {
            nodesApplied++;
            const name = parsed.name as string;
            const impact = parsed.impact as ChainNode["impact"];
            const score = parseFloat(parsed.impact_score ?? "0");
            const priceChange = parseFloat(parsed.price_change ?? "0");
            const reason = (parsed.impact_reason ?? "") as string;
            const path = (parsed.transmission_path ?? "") as string;

            set((s) => {
              const shocks = s.shocks;
              return {
                nodes: s.nodes.map((n) => {
                  if (n.name === name && !shocks.has(name)) {
                    return {
                      ...n,
                      impact,
                      impact_score: score,
                      price_change: priceChange,
                      summary: reason + (path ? ` [${path}]` : ""),
                    };
                  }
                  return n;
                }),
                simulateProgress: {
                  ...s.simulateProgress,
                  phase: "propagating",
                  progress: 0.98,
                  nodesApplied,
                  linksApplied,
                },
              };
            });
            break;
          }

          case "link_impact": {
            linksApplied++;
            const src = parsed.source as string;
            const tgt = parsed.target as string;
            const linkImpact = parsed.impact as ChainLink["impact"];
            const linkReason = (parsed.impact_reason ?? "") as string;

            set((s) => ({
              links: s.links.map((l) => {
                if (l.source === src && l.target === tgt) {
                  return { ...l, impact: linkImpact, impact_reason: linkReason };
                }
                return l;
              }),
              simulateProgress: {
                ...s.simulateProgress,
                phase: "propagating",
                progress: 0.99,
                nodesApplied,
                linksApplied,
              },
            }));
            break;
          }

          case "simulate_complete":
            set({
              status: "ready",
              simulateSummary: (parsed.summary ?? "") as string,
              simulateProgress: {
                phase: "idle",
                tokens: 0,
                progress: 1,
                nodesApplied,
                linksApplied,
              },
            });
            break;

          case "error":
            set({
              status: "ready",
              error: parsed.message || "模拟失败",
              simulateProgress: { phase: "idle", tokens: 0, progress: 0, nodesApplied: 0, linksApplied: 0 },
            });
            break;
        }
      } catch {
        // skip
      }
    }
  }
}
