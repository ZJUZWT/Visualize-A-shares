"""ChainAgent — 产业物理学家级 LLM 推演引擎

核心能力：
1. 递归多跳展开产业链传导
2. 每个环节强制输出物理约束（停产恢复、运输瓶颈、产能天花板等）
3. 每条传导边强制输出传导特性（速度、强度、衰减/放大因素）
4. SSE 流式推送，前端看到图逐步生长（真正流式：每完成一个 node/link 立即推送）
5. 去重环检测 + 名称归一化，避免无限发散和重复节点
"""

from __future__ import annotations

import asyncio
import json
import re

from loguru import logger

from llm.providers import BaseLLMProvider, ChatMessage
from .chain_schemas import (
    ChainExploreRequest,
    ChainExploreResult,
    ChainBuildRequest,
    ChainSimulateRequest,
    ChainNode,
    ChainLink,
    PhysicalConstraint,
)


# ══════════════════════════════════════════════════════════════
# 名称归一化 — 解决 "PVC" vs "PVC（聚氯乙烯）" 等重复节点问题
# ══════════════════════════════════════════════════════════════

# 同义词表：所有别名 → 标准名
# key 是小写的别名，value 是标准名
_SYNONYM_TABLE: dict[str, str] = {}

_SYNONYM_GROUPS: list[tuple[str, list[str]]] = [
    ("PVC", ["聚氯乙烯", "PVC树脂", "聚氯乙烯树脂", "PVC（聚氯乙烯）", "聚氯乙烯（PVC）"]),
    ("PE", ["聚乙烯", "PE树脂", "聚乙烯树脂", "PE（聚乙烯）", "聚乙烯（PE）"]),
    ("PP", ["聚丙烯", "PP树脂", "PP（聚丙烯）", "聚丙烯（PP）"]),
    ("烧碱", ["氢氧化钠", "NaOH", "烧碱（氢氧化钠）", "氢氧化钠（烧碱）", "片碱", "液碱"]),
    ("纯碱", ["碳酸钠", "Na2CO3", "纯碱（碳酸钠）", "碳酸钠（纯碱）", "苏打"]),
    ("电石", ["碳化钙", "CaC2", "电石（碳化钙）", "碳化钙（电石）"]),
    ("乙烯", ["C2H4", "乙烯（C2H4）"]),
    ("丙烯", ["C3H6", "丙烯（C3H6）"]),
    ("甲醇", ["CH3OH", "木醇", "甲醇（CH3OH）"]),
    ("尿素", ["CO(NH2)2", "尿素（CO(NH2)2）", "碳酰胺"]),
    ("多晶硅", ["多晶硅料", "硅料", "多晶硅（硅料）"]),
    ("原油", ["石油", "原油（石油）", "crude oil"]),
    ("天然气", ["LNG", "液化天然气", "天然气（LNG）"]),
    ("铁矿石", ["铁矿", "铁矿石（铁矿）"]),
    ("螺纹钢", ["钢筋", "螺纹钢（钢筋）"]),
    ("锂电池", ["锂离子电池", "动力电池", "锂电池（锂离子电池）"]),
    ("光伏组件", ["太阳能电池板", "太阳能组件", "光伏板"]),
    ("硅片", ["单晶硅片", "硅片（单晶硅片）"]),
    ("磷酸铁锂", ["LFP", "LFP电池", "磷酸铁锂（LFP）"]),
    ("三元材料", ["NCM", "NCA", "三元正极", "三元材料（NCM）"]),
    ("氧化铝", ["Al2O3", "氧化铝（Al2O3）"]),
    ("钛白粉", ["二氧化钛", "TiO2", "钛白粉（二氧化钛）"]),
]

for _std_name, _aliases in _SYNONYM_GROUPS:
    _SYNONYM_TABLE[_std_name.lower()] = _std_name
    for _alias in _aliases:
        _SYNONYM_TABLE[_alias.lower()] = _std_name

# 括号模式
_PAREN_PATTERN = re.compile(r'[（(]([^）)]+)[）)]')


def _normalize_name(raw_name: str) -> str:
    """将节点名归一化为标准名称
    
    规则：
    1. 精确匹配同义词表 → 返回标准名
    2. "A（B）" 格式 → 检查 A 和 B 是否在同义词表中
    3. 去除尾部冗余描述（如 "PVC生产" → "PVC"，保留 >2 字的核心名）
    """
    name = raw_name.strip()
    if not name:
        return name
    
    # 精确匹配
    lower = name.lower()
    if lower in _SYNONYM_TABLE:
        return _SYNONYM_TABLE[lower]
    
    # "A（B）" / "A(B)" → 尝试 A 和 B
    m = _PAREN_PATTERN.search(name)
    if m:
        # 提取括号外部分和括号内部分
        outer = _PAREN_PATTERN.sub('', name).strip()
        inner = m.group(1).strip()
        
        # 先查括号外
        if outer.lower() in _SYNONYM_TABLE:
            return _SYNONYM_TABLE[outer.lower()]
        # 再查括号内
        if inner.lower() in _SYNONYM_TABLE:
            return _SYNONYM_TABLE[inner.lower()]
        # 都不在表里 → 取括号外（更简短的名字）
        return outer
    
    return name


def _build_alias_set(all_nodes: dict[str, ChainNode]) -> dict[str, str]:
    """从已有节点构建运行时别名集合，用于检测新节点是否是已有节点的别名
    
    Returns: {小写别名: 已有节点标准名}
    """
    alias_map: dict[str, str] = {}
    for std_name in all_nodes:
        low = std_name.lower()
        alias_map[low] = std_name
        # 找同义词组
        for grp_std, grp_aliases in _SYNONYM_GROUPS:
            if grp_std == std_name or grp_std.lower() == low:
                for a in grp_aliases:
                    alias_map[a.lower()] = std_name
                break
            for a in grp_aliases:
                if a.lower() == low:
                    alias_map[grp_std.lower()] = std_name
                    for a2 in grp_aliases:
                        alias_map[a2.lower()] = std_name
                    break
    return alias_map


def _auto_correct_relation(source: str, target: str, relation: str, impact_reason: str) -> str:
    """自动纠正 LLM 标注错误的 relation 类型

    典型错误：把上下游关系（乙烯→PVC）标注为 substitute（替代品）。
    LLM 的理由通常是"乙烯法PVC与电石法PVC是替代关系"，但 source→target 实际是原料→产品。

    Returns:
        纠正后的 relation 字符串
    """
    if relation != "substitute" or not impact_reason:
        return relation

    reason_lower = impact_reason.lower()

    # 上下游信号：impact_reason 中暗示 source→target 是原料→产品的关系
    upstream_signals = [
        "原料", "原材料", "成本", "制成", "制造", "生产", "加工",
        "法pvc", "法pe", "法pp", "法生产", "工艺路线", "裂解",
        "聚合", "合成", "冶炼", "提炼", "萃取",
    ]
    is_upstream_relation = any(sig in reason_lower for sig in upstream_signals)
    if not is_upstream_relation:
        return relation  # 没有上下游信号 → 保留 substitute

    # 确认不是真正的产品替代
    true_substitute_signals = [
        "替代品", "可以替代", "互相替代", "功能相同", "性能相似", "可替换",
    ]
    is_true_substitute = any(sig in reason_lower for sig in true_substitute_signals)

    if not is_true_substitute:
        logger.info(
            f"relation 自动纠正: {source}→{target} substitute→upstream "
            f"(reason含上下游信号: {impact_reason[:60]})"
        )
        return "upstream"

    # 两者都有 → 如果说的是"工艺路线替代"而非"产品替代"，source→target 仍是上下游
    route_signals = ["法pvc", "法pe", "法pp", "法生产", "工艺", "路线", "方法"]
    if any(sig in reason_lower for sig in route_signals):
        logger.info(
            f"relation 自动纠正: {source}→{target} substitute→upstream "
            f"(工艺路线替代≠产品替代: {impact_reason[:60]})"
        )
        return "upstream"

    return relation


# ══════════════════════════════════════════════════════════════
# 流式 JSON 增量解析器 — 真正做到"一个节点/一条边生成完就推"
# ══════════════════════════════════════════════════════════════

class _StreamingJsonExtractor:
    """从 LLM 流式 token 中增量提取完整的 JSON 对象
    
    原理：追踪大括号嵌套深度。当我们在 "nodes" 或 "links" 数组中，
    每个 {...} 对象闭合时就立即 yield 出去。
    """
    
    def __init__(self):
        self._buffer = ""
        self._in_string = False
        self._escape = False
        self._brace_depth = 0
        self._bracket_depth = 0
        self._current_array: str = ""  # "nodes" | "links" | ""
        self._object_start = -1
        self._object_depth_start = 0
        self._thinking_done = False
        # 收集完整 raw 用于 fallback
        self._full_raw = ""
    
    def feed(self, chunk: str) -> list[tuple[str, dict]]:
        """喂入一段 token，返回 [(type, parsed_object), ...] 
        type = "node" | "link" | "meta"
        """
        self._full_raw += chunk
        results = []
        
        for ch in chunk:
            self._buffer += ch
            
            # 跳过 <think>...</think> 部分
            if not self._thinking_done:
                if self._buffer.endswith("</think>"):
                    self._buffer = ""
                    self._thinking_done = True
                    continue
                if "<think>" in self._buffer and "</think>" not in self._buffer:
                    continue
                if "<think>" not in self._buffer:
                    self._thinking_done = True
            
            # 处理字符串内容
            if self._escape:
                self._escape = False
                continue
            if ch == '\\' and self._in_string:
                self._escape = True
                continue
            if ch == '"':
                self._in_string = not self._in_string
                continue
            if self._in_string:
                continue
            
            # 检测当前所在数组
            if not self._current_array:
                # 检查是否进入 "nodes" 或 "links" 数组
                if '"nodes"' in self._buffer[-30:] and ch == '[':
                    self._current_array = "nodes"
                    self._bracket_depth = 1
                    continue
                elif '"links"' in self._buffer[-30:] and ch == '[':
                    self._current_array = "links"
                    self._bracket_depth = 1
                    continue
            
            if self._current_array:
                if ch == '[':
                    self._bracket_depth += 1
                elif ch == ']':
                    self._bracket_depth -= 1
                    if self._bracket_depth <= 0:
                        # 数组结束
                        self._current_array = ""
                        self._object_start = -1
                        continue
                
                if ch == '{':
                    if self._object_start < 0:
                        self._object_start = len(self._buffer) - 1
                        self._object_depth_start = 1
                    else:
                        self._object_depth_start += 1
                elif ch == '}':
                    if self._object_start >= 0:
                        self._object_depth_start -= 1
                        if self._object_depth_start == 0:
                            # 一个完整对象！
                            obj_str = self._buffer[self._object_start:]
                            self._object_start = -1
                            try:
                                # 尝试解析
                                obj_str_clean = re.sub(r',\s*([}\]])', r'\1', obj_str)
                                parsed = json.loads(obj_str_clean)
                                obj_type = "node" if self._current_array == "nodes" else "link"
                                results.append((obj_type, parsed))
                            except json.JSONDecodeError:
                                pass  # 解析失败就跳过，等 fallback
        
        return results
    
    def get_full_raw(self) -> str:
        return self._full_raw

# ── 产业物理学家 Prompt ──

# ── 沙盘模式：构建中性网络 ──

CHAIN_BUILD_PROMPT = """你是「产业物理学家」。用户给你一个产业链主体，你要构建它的**中性产业链网络**。

## 主体
{subject}

## ⚠️ 输入类型智能识别（必须先做这一步）
用户输入可能是以下任何一种：
- **公司名**（如"中泰化学"、"宁德时代"、"隆基绿能"）→ 你必须先识别该公司的**主营业务和核心产品**，然后以这些核心产品为中心构建产业链。公司本身作为一个 node_type="company" 的节点出现在网络中，并连接到它的核心产品/原材料节点。
- **股票代码**（如"002092"、"300750"）→ 同上，先查出对应公司，再识别主营业务。
- **原材料/产品**（如"石油"、"锂电池"、"PVC"）→ 直接以此为中心构建产业链。
- **行业**（如"光伏"、"半导体"、"新能源车"）→ 拆解为该行业的核心产品和关键环节。
- **宏观因素**（如"美联储加息"、"地缘冲突"、"汇率贬值"）→ 作为 node_type="macro" 的事件驱动节点，分析它对各行业/商品的传导路径。
- **大宗商品**（如"黄金"、"原油"、"铜"）→ 作为 node_type="commodity" 的核心节点，构建其定价因子、供需链条、相关资产。

**如果输入是公司/股票：** 第一层输出必须包含该公司的核心产品节点（如中泰化学→PVC、烧碱、粘胶纤维），以及上游原材料节点（如原盐、电石、煤炭）。后续层级从这些核心产品节点向上下游展开。

## 当前聚焦节点
{focus_nodes}

## 已有节点（不要重复输出这些节点，但 links 必须引用它们）
{existing_nodes}
**重要**：上面列出的节点已经存在于图谱中。你不需要在 nodes 数组中重复输出它们，但你的 links 数组中 source/target **必须使用这些已有节点的名称**来建立连接。新节点必须通过 links 与已有节点或其他新节点连接，不允许出现孤立节点。

## 关键要求
1. **不要预设任何涨跌方向** — 所有节点 impact 都设为 "neutral"，impact_score 都为 0
2. 构建完整的上下游关系：上游原材料 → 中游加工 → 下游应用 → 终端消费
3. 同时考虑替代品、竞争品、物流环节、副产品
4. 如果主体是公司，还要考虑：同行竞争对手、市占率关系、产能对比
5. 每个节点必须带物理约束（停产恢复/产能/物流/替代/库存/进出口）
6. 每条边必须带传导特性（速度/强度/机制/衰减因素/放大因素）
7. 边的 impact 也设为 "neutral"（冲击传播时再计算）
8. **节点命名规则**：使用最简短的通用名称，**禁止使用括号注释**。例如用"PVC"而不是"PVC（聚氯乙烯）"，用"烧碱"而不是"烧碱（氢氧化钠）"，用"电石"而不是"电石（碳化钙）"。每个概念只能有一个节点。

{focus_area_note}

## 输出格式
直接输出 JSON：
{{
  "nodes": [
    {{
      "name": "节点名称",
      "node_type": "material|industry|company|event|logistics|macro|commodity",
      "impact": "neutral",
      "impact_score": 0.0,
      "summary": "该节点在产业链中的角色（不要写涨跌影响）",
      "representative_stocks": ["600028"],
      "constraint": {{
        "node": "节点名称",
        "shutdown_recovery_time": "...",
        "restart_cost": "...",
        "capacity_ramp_curve": "...",
        "capacity_ceiling": "...",
        "expansion_lead_time": "...",
        "logistics_mode": "...",
        "logistics_bottleneck": "...",
        "logistics_vulnerability": "...",
        "substitution_path": "...",
        "switching_cost": "...",
        "switching_time": "...",
        "inventory_buffer_days": "...",
        "strategic_reserve": "...",
        "import_dependency": "...",
        "export_ratio": "...",
        "key_trade_routes": "..."
      }}
    }}
  ],
  "links": [
    {{
      "source": "源节点",
      "target": "目标节点",
      "relation": "upstream|downstream|substitute|cost_input|byproduct|logistics|competes",
      "impact": "neutral",
      "impact_reason": "具体描述两节点的产业关系（必须包含：运输方式、成本占比、供需依赖度、贸易路径等具体信息。例：'原盐通过铁路运输至中泰化学阿克苏基地，占PVC生产成本约15%，中泰化学自有盐矿供应率约60%'）",
      "confidence": 0.85,
      "transmission_speed": "即时|1-3个月|3-6个月|半年以上",
      "transmission_strength": "强刚性|中等|弱弹性",
      "transmission_mechanism": "成本推动|供给收缩|需求替代|情绪传导|政策驱动",
      "dampening_factors": ["因素1"],
      "amplifying_factors": ["因素1"],
      "constraint": null
    }}
  ],
  "expand_candidates": ["值得继续深挖的节点名称"]
}}

**特别注意 — relation 关系类型严格定义（必须严格遵守，不可混淆）**：

| relation | 含义 | 典型例子 | 绝对禁止 |
|---|---|---|---|
| upstream | A是B的上游原料/供应来源 | 乙烯→PVC（乙烯是PVC的原料）| 不可标注两个同级竞品 |
| downstream | A是B的下游产品/消费去向 | PVC→PVC管材（PVC制成管材）| 不可标注原料到产品 |
| cost_input | A是B的生产成本项 | 电力→电解铝（电是电解铝成本）| 同upstream，但强调成本 |
| byproduct | A是生产B时的副产品 | 烧碱→PVC（氯碱联产副产物）| |
| substitute | A和B是**同级别可互相替代**的产品 | 乙烯法PVC ↔ 电石法PVC | **绝对禁止用于上下游！** |
| competes | A和B是**同类直接竞争关系** | 中泰化学 ↔ 新疆天业 | 只用于同类企业/产品 |
| logistics | A是B的物流/运输环节 | 海运→铁矿石 | |

**⚠️ 关键纠错指南 — substitute 的常见误用**：
- ❌ 错误：`乙烯 →[substitute]→ PVC`（乙烯是原料，PVC是产品，这是上下游关系！）
- ✅ 正确：`乙烯 →[upstream]→ PVC`（乙烯是PVC的上游原料，通过乙烯法路线）
- ❌ 错误：`电石 →[substitute]→ PVC`（电石是原料，不是PVC的替代品！）
- ✅ 正确：`电石 →[upstream]→ PVC`（电石是PVC的上游原料，通过电石法路线）
- ✅ substitute的正确用法：如果图中需要表示"乙烯法"和"电石法"的替代关系，应该新建"乙烯法PVC"和"电石法PVC"两个节点，然后标注 `乙烯法PVC →[substitute]→ 电石法PVC`
- ✅ 判断标准：只有**同级别、可互相替代的产品/工艺/路线**才能用 substitute。如果 A 能制成 B，那 A→B 就是 upstream，不是 substitute！

**特别注意 — 边的 impact_reason 质量要求**：
- 必须写明两个节点之间的物理连接方式（铁路/公路/管道/海运/管输等）
- 必须写明成本占比或供需依赖度的具体数字（如"占生产成本30%"）
- 如果是物流环节，必须写明运距、运输时长、运力瓶颈
- 不要写空泛的"上下游关系"、"原材料供应"等废话
- **企业-商品边的特殊要求**：如果边连接的是企业和商品/原材料节点，必须在 impact_reason 开头明确标注关系角色，使用以下格式之一：
  - "【生产】XX公司是YY的生产商/制造商/供应商，..." — 表示企业**生产/产出**该商品
  - "【消费】XX公司是YY的采购方/消费者/使用方，..." — 表示企业**采购/消费**该商品作为原料
  例如：PVC→中泰化学 的 impact_reason 应写为"【生产】中泰化学是国内PVC龙头生产商，PVC年产能约80万吨，占全国约10%"
  又如：原盐→中泰化学 应写为"【消费】中泰化学采购原盐作为氯碱生产的核心原料，年采购量约..."
  - 对于 relation=cost_input 的边，始终标注"【消费】"
  - 对于 relation=byproduct 的边，始终标注"【生产】\""""

# ── 沙盘模式：冲击传播模拟 ──

CHAIN_SIMULATE_PROMPT = """你是「产业物理学家」。用户已经构建了一个产业链网络，并对某些节点施加了冲击（涨/跌）。你需要根据产业链的物理规律，推演冲击如何在网络中传播。

## 产业链主体
{subject}

## 用户施加的冲击
{shocks_description}

## 当前网络节点（共 {node_count} 个）
{nodes_summary}

## 当前网络边（共 {link_count} 条）
{links_summary}

## 你的任务
根据产业链的物理约束和传导特性，计算冲击源对**每一个节点**和**每一条边**的传导影响。

## ⚠️ 核心规则 — 价格传导 vs 利好利空 是两个不同维度

### 规则一：商品/材料的价格沿产业链**同向传导**
- 原油涨价 → 石脑油涨价 → 乙烯涨价 → PE涨价（成本推升，同向）
- 铜涨价 → 电缆涨价 → 家电成本上升（同向）
- 替代品也同向：A涨 → B也涨（需求转移推高B价格）
- **禁止出现「上游涨价→下游跌价」，这在商品间是不可能的**

### 规则二：企业的利好/利空由其与商品的关系决定
- 上游原料涨价 → 企业成本上升 → **利空**（impact=hurt）
- 下游产品涨价 → 企业售价提升 → **利好**（impact=benefit）
- 替代品涨价 → 企业产品需求增加 → **利好**
- 综合判断：企业的 impact_score 综合考虑所有上下游价格变动

### 规则三：物理约束与衰减
1. **物理约束衰减**：库存缓冲、长协锁价会削弱传导；产能紧张、无替代会放大传导
2. **传导衰减**：离冲击源越远，影响越弱（除非有放大因素）
3. **多冲击叠加**：多个冲击源同时影响一个节点时，综合考虑方向和强度

## ⚠️ 关键约束 — 名称精确匹配
- `node_impacts` 中的每个 `name` 必须**完全等于**上方"当前网络节点"列表中的某个节点名，不能多字少字
- `link_impacts` 中的每个 `source`/`target` 必须**完全等于**上方"当前网络边"列表中的 source→target，不能颠倒或改写
- **你必须为上方列出的每一个节点和每一条边都输出影响**（冲击源本身除外）
- 如果某个节点确实几乎不受影响，impact_score 可以设为接近 0 的小数（如 0.02），但仍然要输出

## 输出格式
输出完整 JSON，覆盖所有节点和所有边：
{{
  "node_impacts": [
    {{
      "name": "（必须精确匹配节点名）",
      "impact": "benefit|hurt|neutral",
      "impact_score": 0.65,
      "price_change": 0.45,
      "impact_reason": "石油涨价 → 乙烯价格跟涨约45%（成本推升）→ 但对乙烯行业利空（成本挤压利润）",
      "transmission_path": "石油 → 石脑油 → 乙烯"
    }}
  ],
  "link_impacts": [
    {{
      "source": "（必须精确匹配边的source）",
      "target": "（必须精确匹配边的target）",
      "impact": "positive|negative|neutral",
      "impact_reason": "成本直接推升，价格同向传导"
    }}
  ],
  "summary": "整体传导的一句话总结"
}}

**字段说明**：
- `price_change`：该节点的**价格变动**，-1.0~+1.0。商品/材料节点填价格涨跌幅度（同向传导），企业节点填0
- `impact` + `impact_score`：对该节点的**利好/利空**程度。商品节点的impact跟价格方向一致；企业节点的impact取决于上下游价格变动对其利润的影响
- 边的 `impact`：positive=利好方向传导，negative=利空方向传导"""


CHAIN_EXPLORE_PROMPT = """你是「产业物理学家」，不是普通的行业分析师。你必须像化工厂厂长+航运CEO+贸易商一样思考产业链。

## 当前事件
{event}

## 当前聚焦节点
{focus_nodes}

## 已经分析过的节点（不要重复）
{explored_nodes}

## 你的任务
分析上述事件对聚焦节点的**直接上下游**影响，生成新的传导节点和边。

## 关键要求 — 物理约束思维（这是你和普通分析师的核心区别）
对每个新发现的产业环节，你**必须**思考并输出：

1. **时间刚性**：该环节停产后恢复需要多久？为什么？（物理/化学/工程原因）
2. **产能天花板**：全球/中国产能多少？利用率？新建产能需要几年？
3. **物流约束**：原材料/产品怎么运输？瓶颈在哪？（航线、港口、管道、运力）
4. **替代弹性**：有没有替代路线？切换成本多高？需要多久？
5. **库存缓冲**：行业库存通常能撑多久？有战略储备吗？
6. **进出口依存**：进口依存度多少？出口占比多少？关键贸易路线？

**节点命名规则**：使用最简短的通用名称，**禁止使用括号注释**。例如用"PVC"而不是"PVC（聚氯乙烯）"。

对每条传导边，你**必须**说明：
- **传导速度**：价格变动多快传导到下游？（即时/1-3个月/半年以上）
- **传导强度**：强刚性（无法回避）/ 中等 / 弱弹性（可吸收）
- **衰减因素**：什么会削弱传导？（库存、套保、长协、政策限价…）
- **放大因素**：什么会放大传导？（集中度高、无替代品、消费刚性…）

{focus_area_note}

## 输出格式
直接输出 JSON，格式如下（不要输出任何其他内容）：
{{
  "nodes": [
    {{
      "name": "节点名称",
      "node_type": "material|industry|company|event|logistics|macro|commodity",
      "impact": "benefit|hurt|neutral|source",
      "impact_score": 0.0,
      "summary": "一句话说明该节点如何受影响",
      "representative_stocks": ["600028"],
      "constraint": {{
        "node": "节点名称",
        "shutdown_recovery_time": "...",
        "restart_cost": "...",
        "capacity_ramp_curve": "...",
        "capacity_ceiling": "...",
        "expansion_lead_time": "...",
        "logistics_mode": "...",
        "logistics_bottleneck": "...",
        "logistics_vulnerability": "...",
        "substitution_path": "...",
        "switching_cost": "...",
        "switching_time": "...",
        "inventory_buffer_days": "...",
        "strategic_reserve": "...",
        "import_dependency": "...",
        "export_ratio": "...",
        "key_trade_routes": "..."
      }}
    }}
  ],
  "links": [
    {{
      "source": "源节点名称",
      "target": "目标节点名称",
      "relation": "upstream|downstream|substitute|cost_input|byproduct|logistics|competes",
      "impact": "positive|negative|neutral",
      "impact_reason": "传导逻辑说明（如果涉及企业和商品，开头用【生产】或【消费】标注角色）",
      "confidence": 0.85,
      "transmission_speed": "即时|1-3个月|3-6个月|半年以上",
      "transmission_strength": "强刚性|中等|弱弹性",
      "transmission_mechanism": "成本推动|供给收缩|需求替代|情绪传导|政策驱动",
      "dampening_factors": ["因素1", "因素2"],
      "amplifying_factors": ["因素1", "因素2"],
      "constraint": {{...}}
    }}
  ],
  "expand_candidates": ["值得继续深挖的节点名称1", "节点名称2"]
}}

**⚠️ relation 类型纠错提醒**：
- substitute 只能用于**同级别可互相替代**的产品/工艺（如 乙烯法PVC ↔ 电石法PVC）
- 如果 A 是 B 的原料，即使存在多条工艺路线，A→B 的 relation 仍然是 upstream 或 cost_input，**绝不是 substitute**
- 例：乙烯→PVC 应标注 upstream（乙烯是PVC原料），不是 substitute"""


CHAIN_RELATE_PROMPT = """你是「产业物理学家」。用户在产业链图中新增了节点「{new_node}」（类型：{new_node_type}）。

## 已有节点列表
{existing_nodes}

## 任务
分析「{new_node}」与上述已有节点之间**是否存在**产业链关系。只输出确实存在关系的边。

## 关系类型（必须严格遵守定义，不可混淆）
- upstream: 上游原料/供应来源（A能制成B → A是B的upstream）
- downstream: 下游产品/消费去向（A由B制成 → B是A的downstream）
- substitute: **仅限同级别可互相替代的产品/工艺**（如乙烯法PVC↔电石法PVC）。⚠️绝不可用于上下游！如果A是B的原料，即使有多条工艺路线，也只能标upstream
- cost_input: 成本输入项（同upstream，但强调成本占比）
- byproduct: 副产品（联产关系）
- logistics: 物流/运输环节
- competes: 同类直接竞争（仅限同类企业/产品间）

## 输出格式
直接输出 JSON：
{{"links": [
  {{
    "source": "源节点",
    "target": "目标节点",
    "relation": "upstream|downstream|substitute|cost_input|byproduct|logistics|competes",
    "impact": "neutral",
    "impact_reason": "具体描述两节点的产业关系（如果涉及企业和商品，开头用【生产】或【消费】标注角色。例：'【生产】中泰化学是PVC龙头生产商'）",
    "confidence": 0.85,
    "transmission_speed": "即时|1-3个月|3-6个月|半年以上",
    "transmission_strength": "强刚性|中等|弱弹性",
    "transmission_mechanism": "成本推动|供给收缩|需求替代|情绪传导|政策驱动",
    "dampening_factors": [],
    "amplifying_factors": []
  }}
]}}

如果没有任何关系，输出 {{"links": []}}。
"""

CHAIN_RELATE_BATCH_PROMPT = """你是「产业物理学家」。以下是一批刚刚通过展开操作新发现的节点，需要你分析它们与**已有图谱节点**之间是否存在跨子网的产业链关系。

## 新发现的节点
{new_nodes}

## 已有图谱节点（展开前就存在的）
{existing_nodes}

## 任务
分析**新节点与已有节点之间**是否存在产业链关系。
- 只分析新节点↔已有节点之间的关系（不要分析新节点之间的关系，那些已经在展开时处理了）
- 只输出确实存在关系的边，不要强行关联
- 每个新节点最多关联 3 条最重要的跨子网关系

## 关系类型（必须严格遵守定义，不可混淆）
- upstream: 上游原料/供应来源（A能制成B → A是B的upstream）
- downstream: 下游产品/消费去向
- substitute: **仅限同级别可互相替代的产品/工艺**。⚠️绝不可用于上下游！
- cost_input: 成本输入项
- byproduct: 副产品
- logistics: 物流/运输环节
- competes: 同类直接竞争

## 输出格式
直接输出 JSON：
{{"links": [
  {{
    "source": "源节点",
    "target": "目标节点",
    "relation": "upstream|downstream|substitute|cost_input|byproduct|logistics|competes",
    "impact": "neutral",
    "impact_reason": "具体描述两节点的产业关系（包含运输方式、成本占比、供需依赖度等。如果涉及企业和商品，开头用【生产】或【消费】标注角色）",
    "confidence": 0.85,
    "transmission_speed": "即时|1-3个月|3-6个月|半年以上",
    "transmission_strength": "强刚性|中等|弱弹性",
    "transmission_mechanism": "成本推动|供给收缩|需求替代|情绪传导|政策驱动",
    "dampening_factors": [],
    "amplifying_factors": []
  }}
]}}

如果没有任何跨子网关系，输出 {{"links": []}}。
"""

CHAIN_REINDEX_PROMPT = """你是「产业物理学家」。用户已经构建了一个产业链图谱，但图中的**关系边可能不完整**——有些节点之间明明存在产业链关系，却没有被连线。

你的任务是**审视所有节点，补全缺失的关系边**。

## 所有节点（共 {node_count} 个）
{all_nodes}

## 已有的边（共 {link_count} 条）
{existing_links}

## 你的任务
1. 仔细检查上面列出的所有节点**两两之间**是否存在但尚未被记录的产业链关系
2. **只输出缺失的新边**，不要重复已有的边
3. 重点关注以下容易被遗漏的关系：
   - **企业-原材料**：企业是某原材料的生产商还是消费者？（常见遗漏：公司节点和商品节点之间没有连线）
   - **替代品/竞品**：同一层级的材料/产品是否可以互相替代？
   - **副产品**：某个生产过程是否有联产品？（如氯碱联产PVC和烧碱）
   - **成本输入**：某原料是否是另一个环节的重要成本项？
   - **物流关系**：是否有运输/物流环节被遗漏？
4. 每条新边的 impact_reason 必须写明具体的产业关系细节（运输方式、成本占比、供需依赖度等）
5. 如果涉及企业和商品，开头用【生产】或【消费】标注角色

## 关系类型（必须严格遵守定义，不可混淆）
- upstream: 上游原料/供应来源（A能制成B → A是B的upstream）
- downstream: 下游产品/消费去向
- substitute: **仅限同级别可互相替代的产品/工艺**。⚠️绝不可用于上下游！
- cost_input: 成本输入项
- byproduct: 副产品（联产关系）
- logistics: 物流/运输环节
- competes: 同类直接竞争（仅限同类企业/产品间）

## 输出格式
直接输出 JSON：
{{"links": [
  {{
    "source": "源节点",
    "target": "目标节点",
    "relation": "upstream|downstream|substitute|cost_input|byproduct|logistics|competes",
    "impact": "neutral",
    "impact_reason": "具体描述两节点的产业关系（包含运输方式、成本占比、供需依赖度等。如果涉及企业和商品，开头用【生产】或【消费】标注角色）",
    "confidence": 0.85,
    "transmission_speed": "即时|1-3个月|3-6个月|半年以上",
    "transmission_strength": "强刚性|中等|弱弹性",
    "transmission_mechanism": "成本推动|供给收缩|需求替代|情绪传导|政策驱动",
    "dampening_factors": [],
    "amplifying_factors": []
  }}
]}}

如果所有关系都已经完整，输出 {{"links": []}}。
"""

class ChainAgent:
    """产业链推演 Agent — 递归多跳展开"""

    def __init__(self, llm: BaseLLMProvider):
        self._llm = llm

    async def explore(self, req: ChainExploreRequest):
        """递归探索产业链传导，yield SSE 事件流（真正流式 + 名称归一化）"""
        all_nodes: dict[str, ChainNode] = {}
        all_links: list[ChainLink] = []
        explored: set[str] = set()
        to_expand: list[str] = []
        depth = 0

        yield {
            "event": "explore_start",
            "data": {"event": req.event, "max_depth": req.max_depth},
        }

        for depth in range(1, req.max_depth + 1):
            if depth == 1:
                focus_nodes = req.start_node if req.start_node else req.event
                focus_list = [focus_nodes]
            else:
                focus_list = to_expand[:5]

            if not focus_list:
                break

            yield {
                "event": "depth_start",
                "data": {"depth": depth, "expanding": focus_list},
            }

            focus_area_note = ""
            if req.focus_area:
                focus_area_note = f"请重点关注与「{req.focus_area}」相关的传导路径。"

            prompt = CHAIN_EXPLORE_PROMPT.format(
                event=req.event,
                focus_nodes="、".join(focus_list),
                explored_nodes="、".join(explored) if explored else "（无）",
                focus_area_note=focus_area_note,
            )

            try:
                # ── 真正流式 ──
                extractor = _StreamingJsonExtractor()
                streamed_any = False

                async for token in self._llm.chat_stream(
                    [ChatMessage(role="user", content=prompt)]
                ):
                    items = extractor.feed(token)
                    for item_type, obj in items:
                        if item_type == "node":
                            raw_name = obj.get("name", "")
                            if not raw_name:
                                continue
                            name = _normalize_name(raw_name)
                            if name in all_nodes:
                                continue
                            constraint = None
                            if obj.get("constraint"):
                                try:
                                    constraint = PhysicalConstraint(**{
                                        k: v for k, v in obj["constraint"].items()
                                        if k in PhysicalConstraint.model_fields
                                    })
                                except Exception:
                                    pass
                            node = ChainNode(
                                id=f"n_{name}",
                                name=name,
                                node_type=obj.get("node_type", "industry"),
                                impact=obj.get("impact", "neutral"),
                                impact_score=float(obj.get("impact_score", 0.0)),
                                depth=depth,
                                representative_stocks=obj.get("representative_stocks", []),
                                constraint=constraint,
                                summary=obj.get("summary", ""),
                            )
                            all_nodes[name] = node
                            streamed_any = True
                            yield {
                                "event": "nodes_discovered",
                                "data": {"depth": depth, "nodes": [node.model_dump()]},
                            }
                        elif item_type == "link":
                            raw_source = obj.get("source", "")
                            raw_target = obj.get("target", "")
                            if not raw_source or not raw_target:
                                continue
                            source = _normalize_name(raw_source)
                            target = _normalize_name(raw_target)
                            if source == target:
                                continue
                            for nm in [source, target]:
                                if nm not in all_nodes:
                                    all_nodes[nm] = ChainNode(id=f"n_{nm}", name=nm, depth=depth)
                            constraint = None
                            if obj.get("constraint"):
                                try:
                                    constraint = PhysicalConstraint(**{
                                        k: v for k, v in obj["constraint"].items()
                                        if k in PhysicalConstraint.model_fields
                                    })
                                except Exception:
                                    pass
                            link_key = (source, target)
                            if link_key in {(l.source, l.target) for l in all_links}:
                                continue
                            corrected_relation = _auto_correct_relation(
                                source, target, obj.get("relation", "upstream"), obj.get("impact_reason", ""),
                            )
                            link = ChainLink(
                                source=source,
                                target=target,
                                relation=corrected_relation,
                                impact=obj.get("impact", "neutral"),
                                impact_reason=obj.get("impact_reason", ""),
                                confidence=float(obj.get("confidence", 0.8)),
                                transmission_speed=obj.get("transmission_speed", ""),
                                transmission_strength=obj.get("transmission_strength", ""),
                                transmission_mechanism=obj.get("transmission_mechanism", ""),
                                dampening_factors=obj.get("dampening_factors", []),
                                amplifying_factors=obj.get("amplifying_factors", []),
                                constraint=constraint,
                            )
                            all_links.append(link)
                            streamed_any = True
                            yield {
                                "event": "links_discovered",
                                "data": {"depth": depth, "links": [link.model_dump()]},
                            }

                # Fallback
                if not streamed_any:
                    raw = extractor.get_full_raw()
                    try:
                        parsed = _lenient_json_loads(raw)
                        if isinstance(parsed, dict):
                            node_evts, link_evts = self._batch_parse_and_yield(
                                parsed, depth, all_nodes, all_links,
                            )
                            for evt in node_evts:
                                yield evt
                            for evt in link_evts:
                                yield evt
                    except Exception:
                        logger.warning(f"ChainAgent explore depth={depth}: 流式+兜底都失败")

                # expand_candidates
                try:
                    raw = extractor.get_full_raw()
                    full_parsed = _lenient_json_loads(raw)
                    if isinstance(full_parsed, dict):
                        candidates = full_parsed.get("expand_candidates", [])
                        to_expand = [c for c in candidates if _normalize_name(c) not in explored]
                except Exception:
                    pass

                explored.update(focus_list)

            except Exception as e:
                logger.error(f"ChainAgent depth={depth} 失败: {e}")
                yield {
                    "event": "error",
                    "data": {"message": f"第{depth}层推演失败: {type(e).__name__}"},
                }
                break

        result = ChainExploreResult(
            event=req.event,
            nodes=list(all_nodes.values()),
            links=all_links,
            depth_reached=min(depth, req.max_depth) if all_nodes else 0,
        )

        yield {
            "event": "explore_complete",
            "data": result.model_dump(),
        }

    async def expand_node(self, event: str, node_name: str, existing_graph: dict):
        """交互式展开单个节点（用户双击触发）"""
        req = ChainExploreRequest(
            event=event,
            start_node=node_name,
            max_depth=1,
        )
        async for evt in self.explore(req):
            yield evt

    # ── 沙盘模式：构建中性网络（真正流式） ──

    async def build(self, req: ChainBuildRequest, known_nodes: list[str] | None = None):
        """构建产业链中性网络 — 真正流式推送

        每完成解析一个 node / link 就立即 yield SSE 事件，
        前端看到节点一个一个跳出来、边一条一条画上去。

        同时做名称归一化去重（PVC vs PVC(聚氯乙烯) → 同一个节点）。

        Args:
            req: 构建请求
            known_nodes: 已存在的节点名列表（expand 场景下传入，让 LLM 复用已有节点建边）
        """
        all_nodes: dict[str, ChainNode] = {}
        all_links: list[ChainLink] = []
        explored: set[str] = set()
        to_expand: list[str] = []

        # 根据输入智能判断节点类型
        root_name = _normalize_name(req.subject)
        root_type = _guess_subject_type(root_name)

        root = ChainNode(
            id=f"n_{root_name}",
            name=root_name,
            node_type=root_type,
            impact="source",
            impact_score=0.0,
            depth=0,
            summary=f"产业链中心：{root_name}",
        )
        all_nodes[root_name] = root

        yield {
            "event": "build_start",
            "data": {"subject": root_name, "max_depth": req.max_depth},
        }
        yield {
            "event": "nodes_discovered",
            "data": {"depth": 0, "nodes": [root.model_dump()]},
        }

        for depth in range(1, req.max_depth + 1):
            if depth == 1:
                focus_list = [root_name]
            else:
                focus_list = to_expand[:5]

            if not focus_list:
                break

            yield {
                "event": "depth_start",
                "data": {"depth": depth, "expanding": focus_list},
            }

            focus_area_note = ""
            if req.focus_area:
                focus_area_note = f"请重点关注与「{req.focus_area}」相关的产业链环节。"

            # ── 方向约束 ──
            direction_note = ""
            if req.expand_direction == "upstream":
                direction_note = "\n\n## ⚠️ 方向约束\n**只找上游**：只输出该节点的上游原材料、上游供应商、成本输入项。不要输出下游产品、下游客户、下游应用。边的 relation 只允许 upstream、cost_input、substitute。"
            elif req.expand_direction == "downstream":
                direction_note = "\n\n## ⚠️ 方向约束\n**只找下游**：只输出该节点的下游产品、下游客户、下游应用场景。不要输出上游原材料、上游供应商。边的 relation 只允许 downstream、byproduct、substitute。"

            # ── 数量约束 ──
            max_nodes_note = ""
            if req.max_nodes and req.max_nodes > 0:
                max_nodes_note = f"\n\n## ⚠️ 数量约束\n本次最多只输出 **{req.max_nodes}** 个新节点。只挑最重要的、与聚焦节点关系最直接的节点。"

            combined_note = focus_area_note + direction_note + max_nodes_note

            # expand 场景下启用精简模式：跳过 constraint 以确保 links 输出完整
            if known_nodes:
                combined_note += (
                    "\n\n## ⚠️ 精简模式（展开场景）\n"
                    "这是扩展已有图谱的场景，**最重要的是补充信息密度，丰富连接关系**。\n"
                    "1. 节点的 `constraint` 字段全部设为 `null`（节省 token，确保 links 不被截断）\n"
                    "2. 节点的 `summary` 只写一句话\n"
                    "3. **必须输出 links 数组**，每个新节点至少有一条边连接到已有节点或聚焦节点\n"
                    "4. 先输出 nodes，再输出 links，最后输出 expand_candidates\n"
                    "5. 新节点数量控制在 3-5 个以内\n"
                    "\n## 💡 补充丰富度指引\n"
                    "**请特别注意挖掘以下信息**（这是扩展的核心价值）：\n"
                    "- **替代路线/工艺**：聚焦节点是否有多种制备方式？（如 PVC 有电石法和乙烯法，要分别建节点并标 substitute）\n"
                    "- **竞争产品/替代品**：同一用途是否有不同材料可选？（如 PVC管 vs PE管 vs PPR管，标 substitute）\n"
                    "- **关键企业**：该环节的龙头企业是谁？产能占比多少？（建 company 节点）\n"
                    "- **成本结构**：哪些是主要成本项？各占比多少？（在 impact_reason 中写明\"占成本XX%\"）\n"
                    "- **副产品**：生产过程有无重要副产物？（如氯碱联产：PVC 与烧碱，标 byproduct）\n"
                    "已有图谱中聚焦节点的连接可能很单薄，你的任务就是让它变得丰满。\n"
                )

            # 合并已探索 + 外部已知节点，让 LLM 复用已有节点名建边
            all_existing = explored | set(known_nodes or [])

            prompt = CHAIN_BUILD_PROMPT.format(
                subject=root_name,
                focus_nodes="、".join(focus_list),
                existing_nodes="、".join(sorted(all_existing)) if all_existing else "（无）",
                focus_area_note=combined_note,
            )

            try:
                # ── 真正流式：边生成边解析边推送 ──
                extractor = _StreamingJsonExtractor()
                streamed_nodes: list[str] = []
                streamed_links: list[tuple[str, str]] = []

                async for token in self._llm.chat_stream(
                    [ChatMessage(role="user", content=prompt)]
                ):
                    items = extractor.feed(token)
                    for item_type, obj in items:
                        if item_type == "node":
                            node = self._parse_node_obj(obj, depth, all_nodes)
                            if node:
                                all_nodes[node.name] = node
                                streamed_nodes.append(node.name)
                                yield {
                                    "event": "nodes_discovered",
                                    "data": {"depth": depth, "nodes": [node.model_dump()]},
                                }
                        elif item_type == "link":
                            link = self._parse_link_obj(obj, depth, all_nodes)
                            if link:
                                link_key = (link.source, link.target)
                                if link_key not in {(l.source, l.target) for l in all_links}:
                                    all_links.append(link)
                                    streamed_links.append(link_key)
                                    yield {
                                        "event": "links_discovered",
                                        "data": {"depth": depth, "links": [link.model_dump()]},
                                    }

                # ── Fallback：如果流式解析器没抓到东西，用完整 JSON 做兜底 ──
                raw = extractor.get_full_raw()
                logger.info(f"ChainAgent build depth={depth}: 流式结果 nodes={len(streamed_nodes)} links={len(streamed_links)}")
                if streamed_links or not streamed_nodes:
                    pass  # 正常
                else:
                    # nodes 有但 links 没有 → 可能流式解析器漏了 links
                    links_pos = raw.find('"links"')
                    logger.debug(f"ChainAgent build depth={depth}: nodes有links无, raw长度={len(raw)}, links位置={links_pos}")

                if not streamed_nodes and not streamed_links:
                    # 完全没抓到 → 用完整 JSON 兜底 nodes + links
                    try:
                        parsed = _lenient_json_loads(raw)
                        if isinstance(parsed, dict):
                            nodes_evt, links_evt = self._batch_parse_and_yield(
                                parsed, depth, all_nodes, all_links,
                            )
                            for evt in nodes_evt:
                                yield evt
                            for evt in links_evt:
                                yield evt
                    except Exception:
                        logger.warning(f"ChainAgent build depth={depth}: 流式+兜底都失败")
                elif streamed_nodes and not streamed_links:
                    # nodes 流式抓到了但 links 没有 → 从完整 JSON 补提取 links
                    logger.info(f"ChainAgent build depth={depth}: 流式漏了 links，兜底补提取")
                    try:
                        parsed = _lenient_json_loads(raw)
                        if isinstance(parsed, dict):
                            _, links_evt = self._batch_parse_and_yield(
                                parsed, depth, all_nodes, all_links,
                            )
                            for evt in links_evt:
                                yield evt
                            logger.info(f"  兜底补提取了 {len(links_evt)} 批 links")
                    except Exception as e:
                        logger.warning(f"ChainAgent build depth={depth}: links 兜底也失败: {e}")

                # ── 从完整响应提取 expand_candidates（流式解析器不处理这个字段）──
                try:
                    raw = extractor.get_full_raw()
                    full_parsed = _lenient_json_loads(raw)
                    if isinstance(full_parsed, dict):
                        candidates = full_parsed.get("expand_candidates", [])
                        to_expand = [c for c in candidates if _normalize_name(c) not in explored]
                except Exception:
                    pass

                explored.update(focus_list)

            except Exception as e:
                logger.error(f"ChainAgent build depth={depth} 失败: {e}")
                yield {
                    "event": "error",
                    "data": {"message": f"第{depth}层构建失败: {type(e).__name__}"},
                }
                break

        yield {
            "event": "build_complete",
            "data": {
                "subject": root_name,
                "node_count": len(all_nodes),
                "link_count": len(all_links),
            },
        }

    # ── 辅助方法：解析单个 node/link 对象 ──

    def _parse_node_obj(
        self, nd: dict, depth: int, all_nodes: dict[str, ChainNode],
    ) -> ChainNode | None:
        """解析一个 node JSON 对象，做名称归一化和去重"""
        raw_name = nd.get("name", "")
        if not raw_name:
            return None
        name = _normalize_name(raw_name)
        if name in all_nodes:
            return None

        constraint = None
        if nd.get("constraint"):
            try:
                constraint = PhysicalConstraint(**{
                    k: v for k, v in nd["constraint"].items()
                    if k in PhysicalConstraint.model_fields
                })
            except Exception:
                pass

        return ChainNode(
            id=f"n_{name}",
            name=name,
            node_type=nd.get("node_type", "industry"),
            impact="neutral",
            impact_score=0.0,
            depth=depth,
            representative_stocks=nd.get("representative_stocks", []),
            constraint=constraint,
            summary=nd.get("summary", ""),
        )

    def _parse_link_obj(
        self, lk: dict, depth: int, all_nodes: dict[str, ChainNode],
    ) -> ChainLink | None:
        """解析一个 link JSON 对象，名称归一化 + 自动补建缺失节点 + relation 纠正"""
        raw_source = lk.get("source", "")
        raw_target = lk.get("target", "")
        if not raw_source or not raw_target:
            return None

        source = _normalize_name(raw_source)
        target = _normalize_name(raw_target)

        # source==target 无意义
        if source == target:
            return None

        # 确保节点存在
        for name in [source, target]:
            if name not in all_nodes:
                all_nodes[name] = ChainNode(
                    id=f"n_{name}", name=name, depth=depth,
                )

        # ── relation 自动纠正 ──
        relation = _auto_correct_relation(
            source, target,
            lk.get("relation", "upstream"),
            lk.get("impact_reason", ""),
        )
        impact_reason = lk.get("impact_reason", "")

        constraint = None
        if lk.get("constraint"):
            try:
                constraint = PhysicalConstraint(**{
                    k: v for k, v in lk["constraint"].items()
                    if k in PhysicalConstraint.model_fields
                })
            except Exception:
                pass

        return ChainLink(
            source=source,
            target=target,
            relation=relation,
            impact="neutral",
            impact_reason=impact_reason,
            confidence=float(lk.get("confidence", 0.8)),
            transmission_speed=lk.get("transmission_speed", ""),
            transmission_strength=lk.get("transmission_strength", ""),
            transmission_mechanism=lk.get("transmission_mechanism", ""),
            dampening_factors=lk.get("dampening_factors", []),
            amplifying_factors=lk.get("amplifying_factors", []),
            constraint=constraint,
        )

    def _batch_parse_and_yield(
        self,
        parsed: dict,
        depth: int,
        all_nodes: dict[str, ChainNode],
        all_links: list[ChainLink],
    ) -> tuple[list[dict], list[dict]]:
        """Fallback：从完整 JSON 一次性解析并返回事件列表"""
        node_events = []
        link_events = []

        new_nodes = []
        for nd in parsed.get("nodes", []):
            node = self._parse_node_obj(nd, depth, all_nodes)
            if node:
                all_nodes[node.name] = node
                new_nodes.append(node)

        if new_nodes:
            node_events.append({
                "event": "nodes_discovered",
                "data": {"depth": depth, "nodes": [n.model_dump() for n in new_nodes]},
            })

        existing_link_keys = {(l.source, l.target) for l in all_links}
        new_links = []
        for lk in parsed.get("links", []):
            link = self._parse_link_obj(lk, depth, all_nodes)
            if link:
                key = (link.source, link.target)
                if key not in existing_link_keys:
                    existing_link_keys.add(key)
                    all_links.append(link)
                    new_links.append(link)

        if new_links:
            link_events.append({
                "event": "links_discovered",
                "data": {"depth": depth, "links": [l.model_dump() for l in new_links]},
            })

        return node_events, link_events

    # ── 沙盘模式：冲击传播模拟 ──

    async def simulate(self, req: ChainSimulateRequest):
        """模拟冲击传播 — 用户设置冲击源，AI 推演传播结果

        yield SSE 事件流（真正流式）：
        - simulate_start
        - simulate_thinking: LLM 生成期间的进度更新（token 计数）
        - node_impact: 每个节点的受冲击状态（逐个推送，带间隔）
        - link_impact: 每条边的传导方向（逐条推送，带间隔）
        - simulate_complete
        - error
        """
        yield {
            "event": "simulate_start",
            "data": {
                "subject": req.subject,
                "shock_count": len(req.shocks),
            },
        }

        # 收集冲击源名称用于后续排除
        shock_names = {s.node_name for s in req.shocks}

        # 构建冲击描述
        shocks_desc = "\n".join(
            f"- {s.node_name}: {'涨' if s.shock > 0 else '跌'} {abs(s.shock)*100:.0f}%"
            + (f" ({s.shock_label})" if s.shock_label else "")
            for s in req.shocks
        )

        # 精简当前网络给 LLM — 用编号方便 LLM 不遗漏
        nodes_summary = "\n".join(
            f"[{i+1}] {n.get('name', '?')} ({n.get('node_type', 'industry')}): "
            f"{n.get('summary', '')}"
            + (f" | 约束: {n.get('constraint_summary', '')}" if n.get('constraint_summary') else "")
            for i, n in enumerate(req.nodes)
        )
        links_summary = "\n".join(
            f"[{i+1}] {l.get('source', '?')} →[{l.get('relation', '?')}]→ {l.get('target', '?')} "
            f"(速度:{l.get('transmission_speed', '?')}, 强度:{l.get('transmission_strength', '?')}, "
            f"机制:{l.get('transmission_mechanism', '?')})"
            for i, l in enumerate(req.links)
        )

        prompt = CHAIN_SIMULATE_PROMPT.format(
            subject=req.subject,
            shocks_description=shocks_desc,
            node_count=len(req.nodes),
            link_count=len(req.links),
            nodes_summary=nodes_summary or "（空）",
            links_summary=links_summary or "（空）",
        )

        try:
            # ── 阶段 1：流式收集 LLM 响应，同时推送思考进度 ──
            chunks: list[str] = []
            token_count = 0
            # 估算总 token 数：每个节点 ~50 token + 每条边 ~30 token + 开头/结尾 ~100
            estimated_total = len(req.nodes) * 50 + len(req.links) * 30 + 100
            last_progress_at = 0  # 上次推送进度时的 token 数

            async for token in self._llm.chat_stream(
                [ChatMessage(role="user", content=prompt)]
            ):
                chunks.append(token)
                token_count += 1
                # 每 20 个 token 推送一次进度
                if token_count - last_progress_at >= 20:
                    last_progress_at = token_count
                    progress = min(0.95, token_count / max(estimated_total, 1))
                    yield {
                        "event": "simulate_thinking",
                        "data": {
                            "tokens": token_count,
                            "progress": round(progress, 2),
                            "phase": "thinking",
                        },
                    }

            raw = "".join(chunks)

            # 推送"解析中"
            yield {
                "event": "simulate_thinking",
                "data": {
                    "tokens": token_count,
                    "progress": 0.96,
                    "phase": "parsing",
                },
            }

            parsed = _lenient_json_loads(raw)

            if not isinstance(parsed, dict):
                yield {
                    "event": "error",
                    "data": {"message": "LLM 返回格式错误"},
                }
                return

            # ── 阶段 2：逐个推送影响（带间隔，产生动画效果）──

            yield {
                "event": "simulate_thinking",
                "data": {
                    "tokens": token_count,
                    "progress": 0.98,
                    "phase": "propagating",
                },
            }

            # 构建节点名集合用于验证
            all_node_names = {n.get("name", "") for n in req.nodes}
            # 构建边 key 集合
            all_link_keys = {
                (l.get("source", ""), l.get("target", ""))
                for l in req.links
            }

            # 计算推送间隔：节点+边总数越多间隔越短，保证总时间在 1~3 秒
            total_items = len(parsed.get("node_impacts", [])) + len(parsed.get("link_impacts", []))
            # 加上可能的补全项
            total_items += len(req.nodes) + len(req.links)
            # 目标总时间 1.5 秒，但每条至少 20ms、最多 120ms
            delay = min(0.12, max(0.02, 1.5 / max(total_items, 1)))

            # 逐节点推送影响
            covered_nodes = set()
            for ni in parsed.get("node_impacts", []):
                name = ni.get("name", "")
                if name:
                    covered_nodes.add(name)
                yield {
                    "event": "node_impact",
                    "data": ni,
                }
                await asyncio.sleep(delay)

            # 为 LLM 遗漏的非冲击源节点补充 neutral
            for n in req.nodes:
                name = n.get("name", "")
                if name and name not in covered_nodes and name not in shock_names:
                    yield {
                        "event": "node_impact",
                        "data": {
                            "name": name,
                            "impact": "neutral",
                            "impact_score": 0.0,
                            "price_change": 0.0,
                            "impact_reason": "未受冲击波显著影响",
                            "transmission_path": "",
                        },
                    }
                    await asyncio.sleep(delay)

            # 逐边推送影响
            covered_links = set()
            for li in parsed.get("link_impacts", []):
                src = li.get("source", "")
                tgt = li.get("target", "")
                if src and tgt:
                    covered_links.add((src, tgt))
                yield {
                    "event": "link_impact",
                    "data": li,
                }
                await asyncio.sleep(delay)

            # 为 LLM 遗漏的边补充 neutral
            for l in req.links:
                key = (l.get("source", ""), l.get("target", ""))
                if key[0] and key[1] and key not in covered_links:
                    yield {
                        "event": "link_impact",
                        "data": {
                            "source": key[0],
                            "target": key[1],
                            "impact": "neutral",
                            "impact_reason": "传导影响较弱",
                        },
                    }
                    await asyncio.sleep(delay)

            yield {
                "event": "simulate_complete",
                "data": {
                    "summary": parsed.get("summary", ""),
                    "node_count": len(parsed.get("node_impacts", [])),
                },
            }

        except Exception as e:
            logger.error(f"ChainAgent simulate 失败: {e}")
            yield {
                "event": "error",
                "data": {"message": f"冲击模拟失败: {type(e).__name__}"},
            }

    async def _collect_llm_response(self, prompt: str) -> str:
        """收集完整 LLM 响应"""
        chunks: list[str] = []
        async for token in self._llm.chat_stream(
            [ChatMessage(role="user", content=prompt)]
        ):
            chunks.append(token)
        return "".join(chunks)

    # ── 放置节点（轻量级：只放置 + 发现关系，不扩展上下游）──

    async def place_node(
        self,
        node_name: str,
        node_type: str,
        existing_nodes: list[str],
    ):
        """只把节点放到图上 + 发现与已有节点的关系，不自动扩展上下游"""
        normalized_name = _normalize_name(node_name)

        # 直接 yield 这个节点本身
        node = ChainNode(
            id=f"n_{normalized_name}",
            name=normalized_name,
            node_type=node_type,
            impact="neutral",
            impact_score=0.0,
            depth=0,
            representative_stocks=[],
            constraint=None,
            summary="",
        )
        yield {
            "event": "nodes_discovered",
            "data": {
                "depth": 0,
                "nodes": [node.model_dump()],
            },
        }

        # 如果有已有节点，用 LLM 发现跨子网关系
        if existing_nodes:
            try:
                existing_str = "\n".join(f"- {n}" for n in existing_nodes[:30])
                prompt = CHAIN_RELATE_PROMPT.format(
                    new_node=normalized_name,
                    new_node_type=node_type,
                    existing_nodes=existing_str,
                )
                raw = await self._collect_llm_response(prompt)
                parsed = _lenient_json_loads(raw)

                relate_links = []
                for lk in parsed.get("links", []):
                    source = _normalize_name(lk.get("source", ""))
                    target = _normalize_name(lk.get("target", ""))
                    if not source or not target or source == target:
                        continue
                    corrected_relation = _auto_correct_relation(
                        source, target, lk.get("relation", "upstream"), lk.get("impact_reason", ""),
                    )
                    link = ChainLink(
                        source=source,
                        target=target,
                        relation=corrected_relation,
                        impact="neutral",
                        impact_reason=lk.get("impact_reason", ""),
                        confidence=float(lk.get("confidence", 0.8)),
                        transmission_speed=lk.get("transmission_speed", ""),
                        transmission_strength=lk.get("transmission_strength", ""),
                        transmission_mechanism=lk.get("transmission_mechanism", ""),
                        dampening_factors=lk.get("dampening_factors", []),
                        amplifying_factors=lk.get("amplifying_factors", []),
                    )
                    relate_links.append(link)

                if relate_links:
                    yield {
                        "event": "links_discovered",
                        "data": {
                            "depth": 0,
                            "links": [l.model_dump() for l in relate_links],
                            "source": "relate",
                        },
                    }
            except Exception as e:
                logger.warning(f"ChainAgent place_node relate 失败: {e}")

        yield {
            "event": "place_node_complete",
            "data": {"node_name": normalized_name},
        }

    # ── 添加节点并发现关系（含扩展1层上下游）──

    async def add_node(
        self,
        node_name: str,
        node_type: str,
        existing_nodes: list[str],
    ):
        """添加一个新节点并用 LLM 发现它与已有节点的关系"""
        normalized_name = _normalize_name(node_name)

        # 阶段 1：build(subject=node_name, depth=1) — 获取 1 层上下游
        build_req = ChainBuildRequest(subject=normalized_name, max_depth=1)
        async for evt in self.build(build_req):
            yield evt

        # 阶段 2：如果有已有节点，用 LLM 发现跨子网关系
        if existing_nodes:
            try:
                existing_str = "\n".join(f"- {n}" for n in existing_nodes[:30])
                prompt = CHAIN_RELATE_PROMPT.format(
                    new_node=normalized_name,
                    new_node_type=node_type,
                    existing_nodes=existing_str,
                )
                raw = await self._collect_llm_response(prompt)
                parsed = _lenient_json_loads(raw)

                relate_links = []
                for lk in parsed.get("links", []):
                    source = _normalize_name(lk.get("source", ""))
                    target = _normalize_name(lk.get("target", ""))
                    if not source or not target or source == target:
                        continue
                    corrected_relation = _auto_correct_relation(
                        source, target, lk.get("relation", "upstream"), lk.get("impact_reason", ""),
                    )
                    link = ChainLink(
                        source=source,
                        target=target,
                        relation=corrected_relation,
                        impact="neutral",
                        impact_reason=lk.get("impact_reason", ""),
                        confidence=float(lk.get("confidence", 0.8)),
                        transmission_speed=lk.get("transmission_speed", ""),
                        transmission_strength=lk.get("transmission_strength", ""),
                        transmission_mechanism=lk.get("transmission_mechanism", ""),
                        dampening_factors=lk.get("dampening_factors", []),
                        amplifying_factors=lk.get("amplifying_factors", []),
                    )
                    relate_links.append(link)

                if relate_links:
                    yield {
                        "event": "links_discovered",
                        "data": {
                            "depth": 0,
                            "links": [l.model_dump() for l in relate_links],
                            "source": "relate",
                        },
                    }
            except Exception as e:
                logger.warning(f"ChainAgent add_node relate 失败: {e}")

        yield {
            "event": "add_node_complete",
            "data": {"node_name": normalized_name},
        }

    # ── 批量 relate：一次 LLM 调用发现多个新节点与已有图的跨子网关系 ──

    async def relate_batch(
        self,
        new_nodes: list[dict],
        existing_nodes: list[str],
    ):
        """批量发现新节点与已有图谱节点之间的跨子网关系
        
        Args:
            new_nodes: [{"name": "xxx", "node_type": "yyy"}, ...]
            existing_nodes: 展开前已有的节点名列表
            
        Yields:
            SSE 事件：links_discovered, relate_batch_complete
        """
        if not new_nodes or not existing_nodes:
            yield {
                "event": "relate_batch_complete",
                "data": {"link_count": 0},
            }
            return

        # 过滤掉新节点中与已有节点重名的
        filtered_new = [n for n in new_nodes if n["name"] not in set(existing_nodes)]
        if not filtered_new:
            yield {
                "event": "relate_batch_complete",
                "data": {"link_count": 0},
            }
            return

        new_nodes_str = "\n".join(
            f"- {n['name']}（{n.get('node_type', 'industry')}）" for n in filtered_new[:15]
        )
        existing_str = "\n".join(f"- {n}" for n in existing_nodes[:30])

        prompt = CHAIN_RELATE_BATCH_PROMPT.format(
            new_nodes=new_nodes_str,
            existing_nodes=existing_str,
        )

        try:
            raw = await self._collect_llm_response(prompt)
            parsed = _lenient_json_loads(raw)

            relate_links = []
            for lk in parsed.get("links", []):
                source = _normalize_name(lk.get("source", ""))
                target = _normalize_name(lk.get("target", ""))
                if not source or not target or source == target:
                    continue
                corrected_relation = _auto_correct_relation(
                    source, target, lk.get("relation", "upstream"), lk.get("impact_reason", ""),
                )
                link = ChainLink(
                    source=source,
                    target=target,
                    relation=corrected_relation,
                    impact="neutral",
                    impact_reason=lk.get("impact_reason", ""),
                    confidence=float(lk.get("confidence", 0.8)),
                    transmission_speed=lk.get("transmission_speed", ""),
                    transmission_strength=lk.get("transmission_strength", ""),
                    transmission_mechanism=lk.get("transmission_mechanism", ""),
                    dampening_factors=lk.get("dampening_factors", []),
                    amplifying_factors=lk.get("amplifying_factors", []),
                )
                relate_links.append(link)

            if relate_links:
                yield {
                    "event": "links_discovered",
                    "data": {
                        "depth": 0,
                        "links": [l.model_dump() for l in relate_links],
                        "source": "relate_batch",
                    },
                }

            yield {
                "event": "relate_batch_complete",
                "data": {"link_count": len(relate_links)},
            }

        except Exception as e:
            logger.warning(f"ChainAgent relate_batch 失败: {e}")
            yield {
                "event": "relate_batch_complete",
                "data": {"link_count": 0, "error": str(type(e).__name__)},
            }

    # ── 重整关系：全图审视，补全缺失边 ──

    async def reindex_links(
        self,
        nodes: list[dict],
        existing_links: list[dict],
    ):
        """审视全图所有节点，补全缺失的关系边

        Args:
            nodes: [{"name": "xxx", "node_type": "yyy"}, ...]
            existing_links: [{"source": "A", "target": "B", "relation": "upstream"}, ...]

        Yields:
            SSE 事件：reindex_start, links_discovered, reindex_complete
        """
        yield {
            "event": "reindex_start",
            "data": {"node_count": len(nodes), "link_count": len(existing_links)},
        }

        if len(nodes) < 2:
            yield {
                "event": "reindex_complete",
                "data": {"new_link_count": 0},
            }
            return

        # 构建节点列表和已有边的描述
        all_nodes_str = "\n".join(
            f"- {n['name']}（{n.get('node_type', 'industry')}）"
            for n in nodes[:50]  # 限制 50 个节点以控制 token
        )
        existing_links_str = "\n".join(
            f"- {l['source']} →[{l.get('relation', '?')}]→ {l['target']}"
            for l in existing_links
        ) if existing_links else "（暂无）"

        # 已有边的 key 集合，用于去重
        existing_keys = {
            (l.get("source", ""), l.get("target", ""))
            for l in existing_links
        }
        # 也加上反向，避免 A→B 和 B→A 重复
        existing_keys_bidir = existing_keys | {(t, s) for s, t in existing_keys}

        # 节点太多时分批（每批最多 25 个节点，避免 prompt 过长）
        node_names = [n["name"] for n in nodes]
        batch_size = 25
        total_new_links = 0

        if len(nodes) <= batch_size:
            # 单批处理
            prompt = CHAIN_REINDEX_PROMPT.format(
                node_count=len(nodes),
                all_nodes=all_nodes_str,
                link_count=len(existing_links),
                existing_links=existing_links_str,
            )

            try:
                raw = await self._collect_llm_response(prompt)
                parsed = _lenient_json_loads(raw)

                new_links = []
                for lk in parsed.get("links", []):
                    source = _normalize_name(lk.get("source", ""))
                    target = _normalize_name(lk.get("target", ""))
                    if not source or not target or source == target:
                        continue
                    if (source, target) in existing_keys_bidir:
                        continue  # 已有此边，跳过

                    corrected_relation = _auto_correct_relation(
                        source, target, lk.get("relation", "upstream"), lk.get("impact_reason", ""),
                    )
                    link = ChainLink(
                        source=source,
                        target=target,
                        relation=corrected_relation,
                        impact="neutral",
                        impact_reason=lk.get("impact_reason", ""),
                        confidence=float(lk.get("confidence", 0.8)),
                        transmission_speed=lk.get("transmission_speed", ""),
                        transmission_strength=lk.get("transmission_strength", ""),
                        transmission_mechanism=lk.get("transmission_mechanism", ""),
                        dampening_factors=lk.get("dampening_factors", []),
                        amplifying_factors=lk.get("amplifying_factors", []),
                    )
                    new_links.append(link)
                    existing_keys_bidir.add((source, target))
                    existing_keys_bidir.add((target, source))

                if new_links:
                    total_new_links += len(new_links)
                    yield {
                        "event": "links_discovered",
                        "data": {
                            "depth": 0,
                            "links": [l.model_dump() for l in new_links],
                            "source": "reindex",
                        },
                    }
            except Exception as e:
                logger.warning(f"ChainAgent reindex_links 失败: {e}")
        else:
            # 分批处理：将节点分成重叠的批次
            for batch_start in range(0, len(nodes), batch_size):
                batch_nodes = nodes[batch_start:batch_start + batch_size]
                batch_names = {n["name"] for n in batch_nodes}

                batch_nodes_str = "\n".join(
                    f"- {n['name']}（{n.get('node_type', 'industry')}）"
                    for n in batch_nodes
                )
                # 只包含涉及本批节点的已有边
                batch_links = [
                    l for l in existing_links
                    if l.get("source", "") in batch_names or l.get("target", "") in batch_names
                ]
                batch_links_str = "\n".join(
                    f"- {l['source']} →[{l.get('relation', '?')}]→ {l['target']}"
                    for l in batch_links
                ) if batch_links else "（暂无）"

                prompt = CHAIN_REINDEX_PROMPT.format(
                    node_count=len(batch_nodes),
                    all_nodes=batch_nodes_str,
                    link_count=len(batch_links),
                    existing_links=batch_links_str,
                )

                try:
                    raw = await self._collect_llm_response(prompt)
                    parsed = _lenient_json_loads(raw)

                    new_links = []
                    for lk in parsed.get("links", []):
                        source = _normalize_name(lk.get("source", ""))
                        target = _normalize_name(lk.get("target", ""))
                        if not source or not target or source == target:
                            continue
                        if (source, target) in existing_keys_bidir:
                            continue

                        corrected_relation = _auto_correct_relation(
                            source, target, lk.get("relation", "upstream"), lk.get("impact_reason", ""),
                        )
                        link = ChainLink(
                            source=source,
                            target=target,
                            relation=corrected_relation,
                            impact="neutral",
                            impact_reason=lk.get("impact_reason", ""),
                            confidence=float(lk.get("confidence", 0.8)),
                            transmission_speed=lk.get("transmission_speed", ""),
                            transmission_strength=lk.get("transmission_strength", ""),
                            transmission_mechanism=lk.get("transmission_mechanism", ""),
                            dampening_factors=lk.get("dampening_factors", []),
                            amplifying_factors=lk.get("amplifying_factors", []),
                        )
                        new_links.append(link)
                        existing_keys_bidir.add((source, target))
                        existing_keys_bidir.add((target, source))

                    if new_links:
                        total_new_links += len(new_links)
                        yield {
                            "event": "links_discovered",
                            "data": {
                                "depth": 0,
                                "links": [l.model_dump() for l in new_links],
                                "source": "reindex",
                            },
                        }
                except Exception as e:
                    logger.warning(f"ChainAgent reindex_links batch 失败: {e}")

        yield {
            "event": "reindex_complete",
            "data": {"new_link_count": total_new_links},
        }

    # ── 批量展开所有叶子节点 ──

    async def expand_all(self, targets: list[tuple[str, str]], existing_nodes: list[str], max_depth: int = 1):
        """并发展开多个节点，每个节点可指定扩展方向 — 真正流式

        Args:
            targets: [(node_name, direction), ...] direction = "upstream" | "downstream" | "both"
            existing_nodes: 已有节点名列表
            max_depth: 每个节点的展开深度（默认 1）

        使用 asyncio.Queue 实现：每个并发 build() 产出的 node/link 立即入队，
        主循环从队列取出后即刻 yield SSE 事件，用户看到图逐步生长而非等全部完成。

        yield SSE 事件流：
        - expand_all_start
        - nodes_discovered, links_discovered (实时推送)
        - expand_all_complete
        """
        # 最多并发 10 个
        targets = targets[:10]
        target_names = [t[0] for t in targets]

        yield {
            "event": "expand_all_start",
            "data": {"targets": target_names, "count": len(targets)},
        }

        # 用队列实现真正流式：生产者(build)→队列→消费者(yield SSE)
        queue: asyncio.Queue[dict | None] = asyncio.Queue()
        pending = len(targets)

        async def _expand_one(node_name: str, direction: str):
            """展开单个节点，事件直接入队"""
            try:
                req = ChainBuildRequest(
                    subject=node_name,
                    max_depth=max_depth,
                    expand_direction=direction,
                )
                async for evt in self.build(req, known_nodes=existing_nodes):
                    await queue.put(evt)
            except Exception as e:
                logger.warning(f"expand_all: {node_name} 失败: {e}")
            finally:
                await queue.put(None)  # 哨兵：标记此任务完成

        # 启动所有并发任务
        for name, direction in targets:
            asyncio.create_task(_expand_one(name, direction))

        # 去重状态
        seen_nodes: set[str] = set(existing_nodes)
        seen_links: set[str] = set()
        finished = 0

        # 从队列消费事件并即刻 yield
        while finished < pending:
            evt = await queue.get()
            if evt is None:
                finished += 1
                continue

            etype = evt.get("event", "")
            if etype == "nodes_discovered":
                raw_nodes = evt["data"].get("nodes", [])
                unique_nodes = [
                    n for n in raw_nodes
                    if n.get("name", "") not in seen_nodes
                ]
                for n in unique_nodes:
                    seen_nodes.add(n.get("name", ""))
                if unique_nodes:
                    yield {
                        "event": "nodes_discovered",
                        "data": {"depth": evt["data"].get("depth", 1), "nodes": unique_nodes},
                    }
            elif etype == "links_discovered":
                raw_links = evt["data"].get("links", [])
                unique_links = []
                for l in raw_links:
                    key = f"{l.get('source', '')}->{l.get('target', '')}"
                    if key not in seen_links:
                        seen_links.add(key)
                        unique_links.append(l)
                if unique_links:
                    yield {
                        "event": "links_discovered",
                        "data": {"depth": evt["data"].get("depth", 1), "links": unique_links},
                    }

        yield {
            "event": "expand_all_complete",
            "data": {"expanded_count": len(targets)},
        }


# ── JSON 解析工具（复用 industry/agent.py 的模式）──

def _extract_json(text: str) -> str:
    """从 LLM 输出提取 JSON（兼容截断输出）"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"<minimax:.*?</minimax:[^>]+>", "", text, flags=re.DOTALL).strip()
    if "<think>" in text and "</think>" not in text:
        # 未闭合的 <think> — 跳过思考内容，取其后的 JSON
        after_tag = text.split("<think>", 1)[-1]
        json_match = re.search(
            r'\{[^{}]*(?:\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}[^{}]*)*\}',
            after_tag, re.DOTALL,
        )
        if json_match:
            text = json_match.group(0)
        else:
            text = ""
    elif "</think>" in text:
        text = text.split("</think>", 1)[-1].strip()

    # 尝试匹配完整的 ```json ... ``` 代码块
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        result = match.group(1).strip()
    else:
        # 没有闭合的 ``` — 可能 JSON 被截断了
        # 尝试匹配只有开头 ``` 的情况
        match_open = re.search(r"```(?:json)?\s*\n?(.*)", text, re.DOTALL)
        if match_open:
            result = match_open.group(1).strip()
        else:
            result = text.strip()

    result = result.replace("\u201c", '"').replace("\u201d", '"')
    result = result.replace("\u2018", "'").replace("\u2019", "'")
    result = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', result)
    return result


def _repair_truncated_json(raw: str) -> str:
    """修复被截断的 JSON — 补齐缺失的括号/引号

    思路：扫描已有内容，统计未闭合的 { } [ ] "，然后在末尾补全。
    这样即使 JSON 在中间被截断，至少 nodes 和 links 数组中已完成的元素能被解析出来。
    """
    # 先去掉末尾可能的残缺 key-value（截断往往发生在某个值中间）
    # 找到最后一个完整的 } 或 ] 或 " 之后的内容
    last_complete = max(
        raw.rfind('}'),
        raw.rfind(']'),
    )
    if last_complete > 0:
        raw = raw[:last_complete + 1]

    # 统计未闭合的括号
    stack = []
    in_string = False
    escape = False
    for ch in raw:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"' and not in_string:
            in_string = True
            continue
        if ch == '"' and in_string:
            in_string = False
            continue
        if in_string:
            continue
        if ch in ('{', '['):
            stack.append(ch)
        elif ch == '}' and stack and stack[-1] == '{':
            stack.pop()
        elif ch == ']' and stack and stack[-1] == '[':
            stack.pop()

    # 如果在字符串中间截断，先闭合字符串
    suffix = ""
    if in_string:
        suffix += '"'

    # 从栈顶向下依次闭合
    for opener in reversed(stack):
        if opener == '{':
            suffix += '}'
        elif opener == '[':
            suffix += ']'

    return raw + suffix


def _lenient_json_loads(text: str) -> dict | list:
    """宽松 JSON 解析 — 支持截断恢复"""
    raw = _extract_json(text)

    # 第一轮：直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 第二轮：去掉尾部逗号
    fixed = re.sub(r',\s*([}\]])', r'\1', raw)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # 第三轮：单引号转双引号
    fixed2 = fixed.replace("'", '"')
    try:
        return json.loads(fixed2)
    except json.JSONDecodeError:
        pass

    # 第四轮：尝试修复截断的 JSON
    repaired = _repair_truncated_json(fixed)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # 第五轮：去掉尾部逗号后再修复
    repaired2 = re.sub(r',\s*([}\]])', r'\1', repaired)
    try:
        return json.loads(repaired2)
    except json.JSONDecodeError:
        pass

    # 最后手段：正则提取最外层 JSON 对象
    m = re.search(r'(\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\})', fixed, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("Chain JSON 解析失败", raw[:200] if raw else "(空)", 0)


# ── 输入类型判断 ──

# 常见行业关键词
_INDUSTRY_KEYWORDS = {
    "光伏", "半导体", "新能源", "锂电", "氢能", "风电", "储能", "芯片",
    "汽车", "房地产", "建材", "钢铁", "有色", "化工", "医药", "白酒",
    "军工", "航空", "航天", "船舶", "农业", "养殖", "种植", "电力",
    "煤炭", "石化", "通信", "计算机", "传媒", "银行", "保险", "证券",
    "消费电子", "面板", "人工智能", "机器人", "无人机",
}

# 常见原材料/商品
_MATERIAL_KEYWORDS = {
    "石油", "原油", "天然气", "煤炭", "铁矿石", "铜", "铝", "锂",
    "镍", "钴", "稀土", "硅", "多晶硅", "电石", "烧碱", "PVC",
    "纯碱", "尿素", "甲醇", "乙烯", "丙烯", "苯", "橡胶", "棉花",
    "大豆", "玉米", "小麦", "猪肉", "生猪", "鸡肉", "白糖", "棕榈油",
    "黄金", "白银", "钢材", "螺纹钢", "水泥", "玻璃", "木材",
    "锂电池", "电池", "芯片",
}


def _guess_subject_type(subject: str) -> str:
    """根据输入文本智能判断主体类型

    Returns:
        "company" | "material" | "industry" | "event"
    """
    s = subject.strip()

    # 1. 股票代码（纯数字 6 位）
    if re.match(r"^\d{6}$", s):
        return "company"

    # 2. 带"股份"/"集团"/"科技"/"化学"/"化工"/"电气"等后缀的 → 公司
    company_suffixes = [
        "股份", "集团", "科技", "化学", "化工", "电气", "电子", "新材料",
        "新能源", "药业", "生物", "通信", "重工", "汽车", "食品", "乳业",
        "地产", "置业", "建设", "矿业", "能源", "控股", "实业", "投资",
        "工业", "技术", "制药", "医疗", "光电", "精密", "环保", "材料",
        "智能", "信息", "网络", "传媒", "航空", "航天",
    ]
    for suffix in company_suffixes:
        if suffix in s and len(s) >= 3:
            return "company"

    # 3. 常见 A 股公司简称（硬匹配一些高频的）
    known_companies = {
        "中泰化学", "万华化学", "宁德时代", "隆基绿能", "比亚迪", "茅台",
        "五粮液", "格力", "美的", "海尔", "中国平安", "招商银行", "中信证券",
        "恒瑞医药", "药明康德", "迈瑞医疗", "中芯国际", "紫光国微",
        "长江电力", "三峡能源", "中国神华", "中国石油", "中国石化",
        "中远海控", "京东方", "TCL", "小米", "腾讯", "阿里", "百度",
        "盐湖股份", "天齐锂业", "赣锋锂业", "北方华创", "中微公司",
        "三一重工", "中联重科", "潍柴动力", "上汽集团", "长城汽车",
    }
    if s in known_companies:
        return "company"

    # 4. 原材料/商品
    for kw in _MATERIAL_KEYWORDS:
        if kw == s or kw in s:
            return "material"

    # 5. 行业
    for kw in _INDUSTRY_KEYWORDS:
        if kw == s or kw in s:
            return "industry"

    # 6. 默认：如果输入较短（2-4字）且不像行业，可能是公司简称
    if 2 <= len(s) <= 4:
        # 短名字更可能是公司简称（如"中泰"、"万华"）
        return "company"

    # 7. fallback
    return "industry"
