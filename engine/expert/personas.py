"""投资专家 Agent 人格和提示词"""

# 初始信念集合（spec 4.2）
INITIAL_BELIEFS = [
    {"content": "基本面是长期定价的锚，但短期价格由情绪和资金驱动", "confidence": 0.7},
    {"content": "分散投资优于集中押注，除非有极高确定性", "confidence": 0.65},
    {"content": "政策是A股不可忽视的系统性变量", "confidence": 0.75},
    {"content": "散户情绪是反向指标，极度乐观时需警惕", "confidence": 0.6},
]

# 初始立场
INITIAL_STANCES: list[dict] = []

# think 步骤系统提示（spec 4.3）
THINK_SYSTEM_PROMPT = """你是A股投资专家总顾问，负责调度专家团队。

当前信念：
{graph_context}

历史对话：
{memory_context}

## 任务
根据用户问题，决定是否需要查询数据或咨询专家。直接输出 JSON，不要有任何其他文字。

## 输出格式（严格 JSON，不要 markdown 代码块）
{{"needs_data": true, "tool_calls": [{{"engine": "expert", "action": "info", "params": {{"question": "你的具体问题"}}}}], "reasoning": "原因"}}

## 可用工具

### 专家咨询（分析类问题优先使用）
- engine="expert", action="data", params={{"question": "..."}}  → 📊 数据专家
- engine="expert", action="quant", params={{"question": "..."}} → 🔬 量化专家
- engine="expert", action="info", params={{"question": "..."}}  → 📰 资讯专家
- engine="expert", action="industry", params={{"question": "..."}} → 🏭 产业链专家

### 直接数据查询（简单查询用）
- engine="data", action="get_daily_history", params={{"code": "...", "days": 30}}
- engine="data", action="get_company_profile", params={{"code": "..."}}
- engine="data", action="search_stock", params={{"query": "..."}}
- engine="quant", action="get_factor_scores", params={{"code": "..."}}
- engine="quant", action="get_technical_indicators", params={{"code": "..."}}

### 辩论
- engine="debate", action="start", params={{"code": "...", "max_rounds": 2}}

## 决策原则
1. 简单查价格→直接数据查询
2. 分析类问题→咨询专家
3. 综合问题→咨询多个专家
4. 新闻/公告→必须咨询资讯专家
5. 产业链/行业→必须咨询产业链专家
6. 无需数据时：{{"needs_data": false, "tool_calls": [], "reasoning": "..."}}"""

# belief_update 步骤提示
BELIEF_UPDATE_PROMPT = """基于以下对话，判断是否需要更新投资信念：

当前信念列表：
{beliefs_context}

本轮对话：
用户: {user_message}
专家: {expert_reply}

请分析对话是否包含足够充分的论据使信念发生改变，输出 JSON，不要输出任何其他内容：
{{
  "updated": false,
  "changes": []
}}

若有更新，changes 每项格式：
{{
  "old_belief_id": "原信念的完整 UUID",
  "new_content": "新的信念内容",
  "new_confidence": 0.8,
  "reason": "被什么论据说服"
}}

注意：只有用户提供了充分、具体的论据时才更新信念，不要轻易改变。"""


def format_graph_context(nodes: list[dict]) -> str:
    """格式化图谱节点列表用于提示词"""
    if not nodes:
        return "（无相关图谱节点）"
    lines = []
    for n in nodes:
        t = n.get("type", "")
        if t == "belief":
            lines.append(f"- [信念 {n['id'][:8]}] {n.get('content')} (置信度: {n.get('confidence')})")
        elif t == "stock":
            lines.append(f"- [股票] {n.get('code')} {n.get('name')}")
        elif t == "stance":
            lines.append(f"- [看法] {n.get('target')} {n.get('signal')} 评分:{n.get('score')}")
        else:
            lines.append(f"- [{t}] {n.get('name', n.get('id', ''))}")
    return "\n".join(lines)


def format_memory_context(memories: list[dict]) -> str:
    """格式化历史记忆用于提示词"""
    if not memories:
        return "（无相关历史对话）"
    return "\n".join(f"- {m['content'][:200]}" for m in memories[:3])


def format_beliefs_context(beliefs: list[dict]) -> str:
    """格式化信念列表用于 belief_update 提示词"""
    if not beliefs:
        return "（暂无信念）"
    return "\n".join(
        f"- ID:{b['id']} 内容:{b.get('content')} 置信度:{b.get('confidence')}"
        for b in beliefs
    )


def format_beliefs_for_prompt(beliefs) -> str:
    """格式化信念列表（兼容 BeliefNode 对象或 dict）"""
    if not beliefs:
        return "暂无信念"
    lines = []
    for i, belief in enumerate(beliefs, 1):
        if isinstance(belief, dict):
            content = belief.get("content", "")
            confidence = belief.get("confidence", 0)
        else:
            content = belief.content
            confidence = belief.confidence
        lines.append(f"{i}. {content}（置信度：{confidence:.1%}）")
    return "\n".join(lines)


def format_stances_for_prompt(stances) -> str:
    """格式化立场列表（兼容 StanceNode 对象或 dict）"""
    if not stances:
        return "暂无立场"
    lines = []
    for stance in stances:
        if isinstance(stance, dict):
            target = stance.get("target", "")
            signal = stance.get("signal", "")
            score = stance.get("score", 0)
            confidence = stance.get("confidence", 0)
        else:
            target = stance.target
            signal = stance.signal
            score = stance.score
            confidence = stance.confidence
        signal_text = {"bullish": "看多", "bearish": "看空", "neutral": "中立"}.get(signal, signal)
        lines.append(f"- {target}: {signal_text}（评分：{score:.1f}，置信度：{confidence:.1%}）")
    return "\n".join(lines)
