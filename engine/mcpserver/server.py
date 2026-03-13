"""
StockTerrain MCP Server — stdio transport

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

import sys
from pathlib import Path

# 确保 engine 目录在 Python 路径中（用于 import config, algorithm 等模块）
_engine_dir = str(Path(__file__).resolve().parent.parent)
if _engine_dir not in sys.path:
    sys.path.insert(0, _engine_dir)

from mcp.server.fastmcp import FastMCP

from .data_access import DataAccess
from . import tools

# ─── 创建 MCP Server ─────────────────────────────────

server = FastMCP(
    "StockTerrain",
    instructions=(
        "StockTerrain MCP Server 提供 A 股全市场数据查询能力，包括：\n"
        "- 全市场概览、聚类结构、因子分析\n"
        "- 个股全维度分析（行情/因子/预测/相似股票）\n"
        "- 条件选股筛选、历史行情查询\n"
        "- 因子 IC 回测、触发地形计算\n\n"
        "后端在线时走 REST API 获取实时数据，离线时自动降级读 DuckDB 历史快照。"
    ),
)

# 全局 DataAccess 实例
_da = DataAccess()


# ─── 注册 10 个 Tool ──────────────────────────────────

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


# ─── 入口 ─────────────────────────────────────────────

def main():
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
