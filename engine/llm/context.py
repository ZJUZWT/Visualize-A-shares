"""
LLM 上下文注入器

将当前地形数据、市场概况、选中股票信息等
自动注入到 LLM 对话的 system prompt 中
"""

from __future__ import annotations

from typing import Any


def build_market_context(
    terrain_summary: dict | None = None,
    selected_stock: dict | None = None,
    cluster_info: dict | None = None,
) -> str:
    """构建市场上下文字符串，注入到 system prompt

    Args:
        terrain_summary: 地形概览数据 {stock_count, cluster_count, top_gainers, top_losers, ...}
        selected_stock: 当前选中的股票信息
        cluster_info: 当前选中/关注的聚类信息
    """
    parts: list[str] = []

    if terrain_summary:
        parts.append(_format_terrain_summary(terrain_summary))
    if selected_stock:
        parts.append(_format_selected_stock(selected_stock))
    if cluster_info:
        parts.append(_format_cluster_info(cluster_info))

    if not parts:
        parts.append("（暂无地形数据，请先生成 3D 地形）")

    return "\n\n".join(parts)


def _format_terrain_summary(data: dict) -> str:
    """格式化地形概览"""
    lines = ["## 当前市场概览"]
    if "stock_count" in data:
        lines.append(f"- 股票总数: {data['stock_count']}")
    if "cluster_count" in data:
        lines.append(f"- 聚类簇数: {data['cluster_count']}")
    if "active_metric" in data:
        metric_names = {
            "pct_chg": "涨跌幅",
            "turnover_rate": "换手率",
            "volume": "成交量",
            "amount": "成交额",
            "pe_ttm": "市盈率(TTM)",
            "pb": "市净率",
            "rise_prob": "明日上涨概率",
        }
        lines.append(f"- 当前 Z 轴指标: {metric_names.get(data['active_metric'], data['active_metric'])}")

    # 涨跌统计
    if "market_stats" in data:
        stats = data["market_stats"]
        if "up_count" in stats:
            lines.append(f"- 上涨: {stats['up_count']} 只 | 下跌: {stats.get('down_count', 0)} 只 | 平盘: {stats.get('flat_count', 0)} 只")
        if "avg_pct_chg" in stats:
            lines.append(f"- 平均涨跌幅: {stats['avg_pct_chg']:.2f}%")

    # 涨幅前 5
    if "top_gainers" in data and data["top_gainers"]:
        lines.append("\n### 涨幅前 5")
        for s in data["top_gainers"][:5]:
            lines.append(f"- {s.get('name', '')}({s.get('code', '')}) {s.get('pct_chg', 0):+.2f}%")

    # 跌幅前 5
    if "top_losers" in data and data["top_losers"]:
        lines.append("\n### 跌幅前 5")
        for s in data["top_losers"][:5]:
            lines.append(f"- {s.get('name', '')}({s.get('code', '')}) {s.get('pct_chg', 0):+.2f}%")

    # 簇概览
    if "cluster_summary" in data and data["cluster_summary"]:
        lines.append("\n### 聚类概览（主要板块）")
        for c in data["cluster_summary"][:8]:
            lines.append(
                f"- 簇#{c.get('cluster_id', '?')}: "
                f"{c.get('size', 0)} 只股票, "
                f"代表: {', '.join(c.get('top_stocks', [])[:3])}"
            )

    return "\n".join(lines)


def _format_selected_stock(stock: dict) -> str:
    """格式化选中的股票"""
    lines = [f"## 当前关注的股票: {stock.get('name', '')}({stock.get('code', '')})"]

    fields = [
        ("pct_chg", "涨跌幅", "%"),
        ("turnover_rate", "换手率", "%"),
        ("volume", "成交量", " 手"),
        ("amount", "成交额", " 元"),
        ("pe_ttm", "市盈率(TTM)", ""),
        ("pb", "市净率", ""),
        ("rise_prob", "明日上涨概率", ""),
    ]

    for key, label, suffix in fields:
        z_key = f"z_{key}"
        val = stock.get(z_key)
        if val is not None:
            if key == "rise_prob":
                pct = (val + 0.5) * 100
                lines.append(f"- {label}: {pct:.1f}%")
            else:
                lines.append(f"- {label}: {val:.2f}{suffix}")

    if stock.get("cluster_id") is not None:
        lines.append(f"- 所属聚类: #{stock['cluster_id']}")

    if stock.get("related_stocks"):
        lines.append("\n### 同簇关联股票")
        for rs in stock["related_stocks"][:5]:
            lines.append(
                f"- {rs.get('name', '')}({rs.get('code', '')}) "
                f"{rs.get('pct_chg', 0):+.2f}%"
            )

    return "\n".join(lines)


def _format_cluster_info(cluster: dict) -> str:
    """格式化聚类信息"""
    lines = [f"## 聚类 #{cluster.get('cluster_id', '?')} 详情"]
    lines.append(f"- 股票数量: {cluster.get('size', 0)}")

    if cluster.get("top_stocks"):
        lines.append(f"- 代表性股票: {', '.join(cluster['top_stocks'][:5])}")

    if cluster.get("feature_profile"):
        lines.append("\n### 特征画像")
        for k, v in cluster["feature_profile"].items():
            lines.append(f"- {k}: {v:.4f}")

    return "\n".join(lines)
