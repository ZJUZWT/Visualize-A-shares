"""
StockScape MCP Server — stdio transport

启动方式:
    cd engine
    python -m mcpserver.server

Claude Code 配置 (.mcp.json):
    {
      "mcpServers": {
        "stockterrain": {
          "command": "python",
          "args": ["-m", "mcpserver.server"],
          "cwd": "/path/to/Visualize-A-shares/engine"
        }
      }
    }
"""

import json
import sys
from pathlib import Path

# 确保 backend 目录在 Python 路径中（用于 import config, engine 等模块）
_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from mcp.server.fastmcp import FastMCP, Context

from .data_access import DataAccess
from . import tools

# ─── 创建 MCP Server ─────────────────────────────────

server = FastMCP(
    "StockScape",
    instructions=(
        "StockScape MCP Server 提供 A 股全市场数据查询能力，包括：\n"
        "- 全市场概览、聚类结构、因子分析\n"
        "- 个股全维度分析（行情/因子/预测/相似股票）\n"
        "- 条件选股筛选、历史行情查询\n"
        "- 因子 IC 回测、触发地形计算\n\n"
        "后端在线时走 REST API 获取实时数据，离线时自动降级读 DuckDB 历史快照。"
    ),
)

# 全局 DataAccess 实例
_da = DataAccess()


# ─── 注册 22 个 Tool ──────────────────────────────────

@server.tool()
def query_market_overview() -> str:
    """获取全市场概览快照。返回股票总数、涨跌统计、全部聚类列表、涨跌幅排行 Top 10。"""
    return tools.query_market_overview(_da)


@server.tool()
def search_stocks(query: str) -> str:
    """搜索股票（模糊匹配代码或名称）。返回匹配的股票列表（最多 20 条），含代码、名称、行业、涨跌幅、所属聚类。"""
    return tools.search_stocks(_da, query)


@server.tool()
def query_cluster(cluster_id: int) -> str:
    """查询指定聚类的完整信息。返回簇内全部成员股票、行业分布 Top 5、平均涨跌幅等。"""
    return tools.query_cluster(_da, cluster_id)


@server.tool()
def query_stock(code: str) -> str:
    """查询单只股票的全维度分析。返回基础行情、所属聚类、因子分值、明日上涨概率、关联/相似股票、近 20 日历史。code 示例: '000001'"""
    return tools.query_stock(_da, code)


@server.tool()
def query_factor_analysis(factor_name: str = "") -> str:
    """查看因子体系全景。不传 factor_name 返回全部 13 个因子概览；传入因子名返回单因子详情。"""
    return tools.query_factor_analysis(_da, factor_name or None)


@server.tool()
def find_similar_stocks(code: str, top_k: int = 10) -> str:
    """跨簇相似股票搜索。基于高维特征空间找出与指定股票最相似的 top_k 只股票。"""
    return tools.find_similar_stocks(_da, code, top_k)


@server.tool()
def query_history(code: str, days: int = 60) -> str:
    """查询股票历史行情数据。返回日线数据（日期/开高低收/成交量/成交额/涨跌幅/换手率）。"""
    return tools.query_history(_da, code, days)


@server.tool()
def query_hourly(code: str, days: int = 5) -> str:
    """查询个股小时线K线数据（60分钟级别）。返回日内OHLCV数据，默认最近5个交易日。code 示例: '600519'"""
    return tools.query_hourly(_da, code, days)


@server.tool()
def run_screen(
    filters: dict,
    sort_by: str = "pct_chg",
    sort_desc: bool = True,
    limit: int = 20,
) -> str:
    """条件选股筛选。Filter DSL: 精确匹配 {"cluster_id": 5}, 范围 {"pe_ttm": {"min": 5, "max": 30}}, 集合 {"cluster_id": {"in": [1,3]}}。可用字段: code, name, cluster_id, pct_chg, turnover_rate, volume, amount, pe_ttm, pb, total_mv, circ_mv, rise_prob, industry"""
    return tools.run_screen(_da, filters, sort_by, sort_desc, limit)


@server.tool()
def run_backtest(rolling_window: int = 20, auto_inject: bool = False) -> str:
    """触发因子 IC 回测。计算各因子 RankIC 时序、ICIR 自适应权重。需要 ≥3 天历史数据。auto_inject=True 会将权重注入预测器（仅在线模式有效）。"""
    return tools.run_backtest(_da, rolling_window, auto_inject)


@server.tool()
def compute_terrain(z_metric: str = "pct_chg", radius_scale: float = 2.0) -> str:
    """触发全量地形计算（仅在线模式）。拉取全市场行情 → 聚类 → 降维 → 插值。返回计算摘要（不含网格数据）。"""
    return tools.compute_terrain(_da, z_metric, radius_scale)


# ─── QuantEngine Tools ──────────────────────────────

@server.tool()
def get_technical_indicators(code: str) -> str:
    """获取个股技术指标（RSI/MACD/布林带）。需要有日线历史数据。code 示例: '600519'"""
    return tools.get_technical_indicators(_da, code)


@server.tool()
def get_factor_scores(code: str) -> str:
    """获取个股多因子评分（13个因子的值、方向、权重）。code 示例: '600519'"""
    return tools.get_factor_scores(_da, code)


@server.tool()
def get_signal_history(code: str, days: int = 30) -> str:
    """查询个股历史量化信号记录。返回最近 N 天的买卖信号。Phase 1 返回空列表。"""
    return tools.get_signal_history(_da, code, days)


# ─── InfoEngine Tools ──────────────────────────────

@server.tool()
def get_news(code: str, limit: int = 20) -> str:
    """获取个股新闻 + 情感分析。返回新闻列表（含情感标注 positive/negative/neutral）和情感统计。code 示例: '600519'"""
    return tools.get_news(_da, code, limit)


@server.tool()
def get_announcements(code: str, limit: int = 10) -> str:
    """获取公司公告 + 情感分析。返回公告列表和情感标注。code 示例: '600519'"""
    return tools.get_announcements(_da, code, limit)


@server.tool()
def assess_event_impact(code: str, event_desc: str) -> str:
    """评估事件对个股的影响。需要描述具体事件内容。返回影响方向(positive/negative/neutral)、强度(high/medium/low)和推理过程。"""
    return tools.assess_event_impact(_da, code, event_desc)


# ─── Agent Tools ────────────────────────────────────

@server.tool()
def submit_analysis(code: str, depth: str = "standard") -> str:
    """触发 AI Multi-Agent 分析。返回分析请求状态。depth: 'quick'|'standard'|'deep'。需要配置 LLM API Key。"""
    return tools.submit_analysis(code, depth)


@server.tool()
def get_analysis_history(code: str, limit: int = 5) -> str:
    """查询个股的历史 AI 分析报告。返回最近 N 条分析结果。"""
    return tools.get_analysis_history(code, limit)


@server.tool()
async def verify_agent_cycle(
    portfolio_id: str,
    as_of_date: str | None = None,
    include_review: bool = True,
    include_weekly: bool = False,
    require_trade: bool = False,
    timeout_seconds: int = 30,
) -> str:
    """验证 Main Agent 一次真实轮回是否能跑通，并返回 pass/warn/fail 与关键证据。"""
    from . import agent_verification

    return await agent_verification.verify_agent_cycle(
        portfolio_id=portfolio_id,
        as_of_date=as_of_date,
        include_review=include_review,
        include_weekly=include_weekly,
        require_trade=require_trade,
        timeout_seconds=timeout_seconds,
    )


@server.tool()
async def inspect_agent_snapshot(
    portfolio_id: str,
    run_id: str | None = None,
) -> str:
    """聚合当前 Main Agent 的 state、latest run、ledger、review 和 memories 快照。"""
    from . import agent_verification

    return await agent_verification.inspect_agent_snapshot(
        portfolio_id=portfolio_id,
        run_id=run_id,
    )


@server.tool()
async def prepare_demo_agent_portfolio(
    scenario_id: str = "demo-evolution",
) -> str:
    """准备一套 deterministic demo portfolio 基线，用于后续 Main Agent 进化闭环验证。"""
    from . import agent_verification

    return await agent_verification.prepare_demo_agent_portfolio(
        scenario_id=scenario_id,
    )


@server.tool()
async def verify_demo_agent_cycle(
    scenario_id: str = "demo-evolution",
    timeout_seconds: int = 30,
) -> str:
    """使用 deterministic demo scenario 触发并验证 Main Agent 完整进化闭环。"""
    from . import agent_verification

    return await agent_verification.verify_demo_agent_cycle(
        scenario_id=scenario_id,
        timeout_seconds=timeout_seconds,
    )


# ─── IndustryEngine Tools ──────────────────────────────

@server.tool()
def query_industry_cognition(target: str) -> str:
    """获取产业链认知。输入股票代码（如 '600519'）或行业名（如 '半导体'），返回产业链结构、供需格局、周期定位、认知陷阱等。"""
    return tools.get_industry_cognition(_da, target)


@server.tool()
def query_industry_mapping(industry: str = "") -> str:
    """查询行业板块列表及成分股。不传 industry 返回所有行业概览；传入行业名返回该行业全部成分股。"""
    return tools.get_industry_mapping_tool(_da, industry)


@server.tool()
def query_capital_structure(code: str) -> str:
    """获取个股资金构成分析。汇聚主力资金流向、北向持股、融资融券、换手率数据。code 示例: '600519'"""
    return tools.get_capital_structure_tool(_da, code)


# ─── Debate Tools ────────────────────────────────────

@server.tool()
async def start_debate(code: str | int, max_rounds: int = 3, ctx: Context = None) -> str:
    """发起专家辩论（多头 vs 空头 + 散户/主力观察员 + 裁判）。需要后端在线且配置 LLM API Key。code 示例: '600519'"""
    return await tools.start_debate_async(_da, str(code), max_rounds, ctx)


@server.tool()
def get_debate_status(debate_id: str) -> str:
    """查询辩论进度。返回当前轮次、状态、是否有一方认输等信息。debate_id 格式: '{code}_{YYYYMMDDHHMMSS}'"""
    return tools.get_debate_status(_da, debate_id)


@server.tool()
def get_debate_transcript(debate_id: str, round: int | None = None, role: str | None = None) -> str:
    """获取辩论记录，支持按轮次和角色过滤。role 可选: bull_expert, bear_expert, retail_investor, smart_money"""
    return tools.get_debate_transcript(_da, debate_id, round, role)


@server.tool()
def get_judge_verdict(debate_id: str) -> str:
    """获取裁判最终总结。返回综合信号、多空核心论点、风险提示、辩论质量评估等。"""
    return tools.get_judge_verdict(_da, debate_id)


# ─── Multi-Expert Tool ─────────────────────────────────

@server.tool()
async def ask_expert(
    expert_type: str,
    question: str,
    ctx: Context = None,
) -> str:
    """向指定专家提问。expert_type 可选: 'data'(数据专家)、'quant'(量化专家)、'info'(资讯专家)、'industry'(产业链专家)、'rag'(投资顾问/RAG)。
    各专家擅长领域:
    - data: 行情查询、股票搜索、聚类分析、全市场概览
    - quant: 技术指标、因子评分、IC回测、条件选股
    - info: 新闻情感、公告解读、事件影响评估
    - industry: 行业认知、产业链映射、资金构成、周期分析
    - rag: 自由对话、知识图谱、信念系统、综合分析"""
    import httpx

    valid_types = ("data", "quant", "info", "industry", "rag")
    if expert_type not in valid_types:
        return json.dumps(
            {"error": f"无效专家类型: {expert_type}，可选: {', '.join(valid_types)}"},
            ensure_ascii=False,
        )

    if not _da.is_online():
        return json.dumps(
            {"error": "后端未运行，无法使用专家对话", "hint": "请先启动 engine: `cd engine && python main.py`"},
            ensure_ascii=False,
        )

    try:
        lines = []
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            async with client.stream(
                "POST",
                f"{_da._api_base}/api/v1/expert/chat/{expert_type}",
                json={"message": question},
            ) as resp:
                resp.raise_for_status()
                event_type = None
                data_buf = ""

                async for line in resp.aiter_lines():
                    if line.startswith("event: "):
                        event_type = line[7:].strip()
                    elif line.startswith("data: "):
                        data_buf = line[6:]
                    elif line == "" and event_type and data_buf:
                        try:
                            data = json.loads(data_buf)
                        except json.JSONDecodeError:
                            event_type = None
                            data_buf = ""
                            continue

                        if event_type == "tool_call":
                            engine = data.get("engine", "")
                            action = data.get("action", "")
                            if ctx:
                                await ctx.log("info", f"🔧 调用工具: {engine}.{action}")

                        elif event_type == "tool_result":
                            summary = data.get("summary", "")[:100]
                            if ctx:
                                await ctx.log("info", f"✅ 工具结果: {summary}")

                        elif event_type == "reply_complete":
                            lines.append(data.get("full_text", ""))

                        elif event_type == "error":
                            return json.dumps(
                                {"error": data.get("message", "专家对话失败")},
                                ensure_ascii=False,
                            )

                        event_type = None
                        data_buf = ""

        return "\n".join(lines) if lines else "专家未返回回复"

    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"请求失败: {e}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"专家对话失败: {e}"}, ensure_ascii=False)


@server.tool()
def list_experts() -> str:
    """列出所有可用的专家类型及其擅长领域。"""
    from engine.expert.engine_experts import get_expert_profiles
    profiles = get_expert_profiles()
    lines = ["# 可用专家列表\n"]
    for p in profiles:
        lines.append(f"## {p['icon']} {p['name']} (`{p['type']}`)")
        lines.append(f"- 擅长: {p['description']}")
        lines.append(f"- 示例问题: {', '.join(p['suggestions'][:2])}")
        lines.append("")
    return "\n".join(lines)


# ─── 入口 ─────────────────────────────────────────────

def main():
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
