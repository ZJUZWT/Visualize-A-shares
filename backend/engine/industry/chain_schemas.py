"""产业链推演数据结构 — 带物理约束的产业认知模型

核心理念：产业链不只是「谁连着谁」（拓扑），
而是「这个连接有什么约束条件」（物理性质）。

每个产业环节有：
- 时间刚性（停产恢复周期）
- 产能天花板（扩产周期）
- 物流瓶颈（运输约束）
- 替代弹性（可替代路径）
- 库存缓冲（能撑多久）

每条传导链有：
- 传导速度（多快影响下游）
- 传导强度（影响多大）
- 衰减/放大因素
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PhysicalConstraint(BaseModel):
    """产业环节的物理/经济约束 — 产业专家与普通分析师的核心认知差距"""

    node: str                                       # 产业环节名称

    # ── 时间刚性 ──
    shutdown_recovery_time: str = ""                # "冷启动需2-4周"
    restart_cost: str = ""                          # "重启一次需数千万元"
    capacity_ramp_curve: str = ""                   # "复产后3-6个月爬坡到满产"

    # ── 产能约束 ──
    capacity_ceiling: str = ""                      # "全球产能2.1亿吨，利用率87%"
    expansion_lead_time: str = ""                   # "新建产能需3-5年"

    # ── 物流瓶颈 ──
    logistics_mode: str = ""                        # "VLCC海运/管道/铁路/公路"
    logistics_bottleneck: str = ""                  # "马六甲海峡/苏伊士运河瓶颈"
    logistics_vulnerability: str = ""               # "单一海峡封锁可致30%供给中断"

    # ── 替代弹性 ──
    substitution_path: str = ""                     # "煤制路线在油价>80美元时有竞争力"
    switching_cost: str = ""                        # "油转煤需要全新装置，不可逆"
    switching_time: str = ""                        # "新建煤化工项目3-4年"

    # ── 库存缓冲 ──
    inventory_buffer_days: str = ""                 # "全球库存覆盖30-45天消费"
    strategic_reserve: str = ""                     # "中国战略储备约XX万吨"

    # ── 进出口依存 ──
    import_dependency: str = ""                     # "中国原油对外依存度72%"
    export_ratio: str = ""                          # "出口占产量15%"
    key_trade_routes: str = ""                      # "中东→马六甲→中国，占进口60%"


class ChainNode(BaseModel):
    """产业链图谱节点"""

    id: str                                         # 节点唯一ID（如 "n_石油"）
    name: str                                       # 显示名称
    node_type: str = "industry"                     # industry | material | company | event | logistics | macro | commodity
    impact: str = "neutral"                         # benefit | hurt | neutral | source
    impact_score: float = 0.0                       # -1.0(极度利空) ~ +1.0(极度利好)
    price_change: float = 0.0                       # -1.0(暴跌) ~ +1.0(暴涨)，商品价格变动
    depth: int = 0                                  # 距事件源的跳数
    representative_stocks: list[str] = Field(default_factory=list)  # A股代码列表
    constraint: PhysicalConstraint | None = None    # 该节点的物理约束（可选）
    summary: str = ""                               # 一句话总结该节点受到的影响


class ChainLink(BaseModel):
    """产业链传导边 — 带物理约束"""

    source: str                                     # 源节点名称
    target: str                                     # 目标节点名称
    relation: str                                   # upstream | downstream | substitute | cost_input | byproduct | logistics | competes

    # ── 影响方向 ──
    impact: str = "neutral"                         # positive | negative | neutral
    impact_reason: str = ""                         # 传导逻辑（1-2句话）
    confidence: float = 0.8                         # 置信度 0-1

    # ── 传导特性（核心升级）──
    transmission_speed: str = ""                    # "即时/1-3个月/半年以上"
    transmission_strength: str = ""                 # "强刚性/中等/弱弹性"
    transmission_mechanism: str = ""                # "成本推动/供给收缩/需求替代/情绪传导"
    dampening_factors: list[str] = Field(default_factory=list)   # 衰减因素
    amplifying_factors: list[str] = Field(default_factory=list)  # 放大因素

    # ── 物理约束 ──
    constraint: PhysicalConstraint | None = None    # 目标环节的物理约束


class ChainExploreRequest(BaseModel):
    """产业链探索请求"""

    event: str = Field(description="触发事件，如'石油涨价'、'台海紧张'")
    start_node: str = ""                            # 可选起点节点（如"石油"），为空则AI自行判断
    max_depth: int = Field(default=3, ge=1, le=6)   # 最大展开深度
    focus_area: str = ""                            # 可选聚焦领域（如"化工"、"运输"）


class ChainExploreResult(BaseModel):
    """产业链探索完整结果"""

    event: str
    nodes: list[ChainNode] = Field(default_factory=list)
    links: list[ChainLink] = Field(default_factory=list)
    depth_reached: int = 0
    reasoning_summary: str = ""                     # AI的推理总结


# ── 沙盘模式（Build + Simulate）──────────────────────────

class ChainBuildRequest(BaseModel):
    """构建产业链网络请求 — 输入任何"东西"（公司/股票/原材料/行业/宏观因素/大宗商品），构建其产业链网络"""

    subject: str = Field(description="产业链主体：公司名(中泰化学)、股票代码(002092)、原材料(石油)、行业(光伏)、宏观(美联储加息)、大宗(黄金)均可")
    max_depth: int = Field(default=1, ge=1, le=6)
    focus_area: str = ""
    expand_direction: str = Field(default="both", description="展开方向：upstream=只找上游, downstream=只找下游, both=全部")
    max_nodes: int = Field(default=0, ge=0, le=20, description="每层最多返回的节点数，0=不限制（LLM自行决定）")


class NodeShock(BaseModel):
    """用户对某个节点施加的冲击"""

    node_name: str                                  # 节点名
    shock: float = Field(ge=-1.0, le=1.0)           # -1.0=暴跌 ~ +1.0=暴涨
    shock_label: str = ""                           # 可选描述，如"涨价50%"


class ChainSimulateRequest(BaseModel):
    """冲击传播模拟请求 — 用户设置冲击源，AI 推演传播"""

    subject: str = Field(description="产业链主体")
    shocks: list[NodeShock] = Field(min_length=1)   # 至少一个冲击源
    nodes: list[dict] = Field(default_factory=list)  # 当前网络中所有节点（精简）
    links: list[dict] = Field(default_factory=list)  # 当前网络中所有边（精简）
