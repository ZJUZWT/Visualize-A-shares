"""
输出格式化 — AI 友好的 Markdown 表格 + 摘要文本

规则：
1. 表格优先：股票列表用 Markdown 表格
2. 关键数字突出：涨跌幅带 ± 号和语义标注
3. 摘要在前：先给结论性摘要，再给详细数据
4. 数据量控制：单次返回不超过 50 只股票详情
5. 离线标注：离线模式下缺失数据明确标注
"""


def fmt_pct(val: float | None) -> str:
    """格式化涨跌幅，带语义标注"""
    if val is None:
        return "N/A"
    v = float(val)
    if v >= 9.5:
        return f"涨停 +{v:.2f}%"
    elif v >= 5:
        return f"大涨 +{v:.2f}%"
    elif v >= 2:
        return f"上涨 +{v:.2f}%"
    elif v > 0:
        return f"微涨 +{v:.2f}%"
    elif v == 0:
        return "平盘 0.00%"
    elif v > -2:
        return f"微跌 {v:.2f}%"
    elif v > -5:
        return f"下跌 {v:.2f}%"
    elif v > -9.5:
        return f"大跌 {v:.2f}%"
    else:
        return f"跌停 {v:.2f}%"


def fmt_number(val: float | None, unit: str = "", decimals: int = 2) -> str:
    """格式化数字，大数自动转换单位"""
    if val is None:
        return "N/A"
    v = float(val)
    if abs(v) >= 1e8:
        return f"{v / 1e8:.{decimals}f}亿{unit}"
    elif abs(v) >= 1e4:
        return f"{v / 1e4:.{decimals}f}万{unit}"
    else:
        return f"{v:.{decimals}f}{unit}"


def fmt_prob(val: float | None) -> str:
    """格式化概率"""
    if val is None:
        return "N/A"
    return f"{float(val):.1%}"


def stock_table(stocks: list[dict], columns: list[str] | None = None) -> str:
    """生成股票 Markdown 表格"""
    if not stocks:
        return "(无数据)"

    if columns is None:
        columns = ["code", "name", "pct_chg", "cluster_id"]

    col_labels = {
        "code": "代码",
        "name": "名称",
        "pct_chg": "涨跌幅",
        "cluster_id": "聚类",
        "industry": "行业",
        "turnover_rate": "换手率",
        "volume": "成交量",
        "amount": "成交额",
        "pe_ttm": "PE(TTM)",
        "pb": "PB",
        "total_mv": "总市值",
        "circ_mv": "流通市值",
        "rise_prob": "上涨概率",
        "price": "价格",
    }

    # Header
    header = " | ".join(col_labels.get(c, c) for c in columns)
    sep = " | ".join("---" for _ in columns)
    lines = [header, sep]

    for s in stocks:
        cells = []
        for c in columns:
            val = s.get(c) or s.get(f"z_{c}")
            if c == "pct_chg":
                cells.append(fmt_pct(val))
            elif c in ("total_mv", "circ_mv", "amount"):
                cells.append(fmt_number(val))
            elif c == "rise_prob":
                cells.append(fmt_prob(val))
            elif c in ("turnover_rate",):
                cells.append(f"{float(val):.2f}%" if val else "N/A")
            elif c in ("pe_ttm", "pb"):
                cells.append(f"{float(val):.2f}" if val else "N/A")
            elif c == "cluster_id":
                cells.append(str(int(val)) if val is not None else "噪声")
            else:
                cells.append(str(val) if val is not None else "N/A")
        lines.append(" | ".join(cells))

    return "\n".join(lines)


def cluster_table(clusters: list[dict]) -> str:
    """生成聚类摘要 Markdown 表格"""
    if not clusters:
        return "(无聚类数据)"

    header = "聚类ID | 数量 | 语义标签 | 代表股票"
    sep = "--- | --- | --- | ---"
    lines = [header, sep]

    for c in clusters:
        cid = c.get("cluster_id", c.get("id", "?"))
        size = c.get("size", c.get("count", 0))
        label = c.get("semantic_label", c.get("label", ""))
        # 代表股票取前3
        reps = c.get("representative_stocks", c.get("top_stocks", []))
        if isinstance(reps, list):
            rep_str = ", ".join(
                f"{r.get('name', r.get('code', ''))}" for r in reps[:3]
            ) if reps else ""
        else:
            rep_str = str(reps)
        lines.append(f"{cid} | {size} | {label} | {rep_str}")

    return "\n".join(lines)


def factor_table(factors: list[dict]) -> str:
    """生成因子分析 Markdown 表格"""
    if not factors:
        return "(无因子数据)"

    header = "因子 | 方向 | 分组 | 权重 | 描述"
    sep = "--- | --- | --- | --- | ---"
    lines = [header, sep]

    for f in factors:
        name = f.get("name", "")
        direction = "+" if f.get("direction", 1) > 0 else "-"
        group = f.get("group", "")
        weight = f"{f.get('weight', 0):.4f}"
        desc = f.get("desc", "")
        lines.append(f"{name} | {direction} | {group} | {weight} | {desc}")

    return "\n".join(lines)


def offline_warning(tool_name: str, missing: str = "") -> str:
    """离线模式警告前缀"""
    msg = f"[离线模式] 部分数据不可用"
    if missing:
        msg += f"（缺失：{missing}）"
    return msg


def error_msg(error_type: str, description: str, suggestion: str) -> str:
    """统一错误格式"""
    return f"❌ [{error_type}] {description}\n💡 {suggestion}"
