"""
MCP Tools — 22 个 Tool 实现

每个 tool 返回 AI 友好的 Markdown 文本（非原始 JSON）。
在线模式优先走 REST API，离线自动降级到 DuckDB read-only。
"""

import json
from pathlib import Path

import pandas as pd
from loguru import logger

from .data_access import DataAccess
from .formatters import (
    fmt_pct, fmt_number, fmt_prob,
    stock_table, cluster_table, factor_table,
    offline_warning, error_msg,
)

# 公司概况缓存
from data_engine.precomputed import load_profiles as _load_profiles_from_engine

_profiles: dict[str, dict] | None = None


def _load_profiles() -> dict[str, dict]:
    global _profiles
    if _profiles is not None:
        return _profiles
    _profiles = _load_profiles_from_engine()
    return _profiles


def _enrich_industry(stocks: list[dict]) -> list[dict]:
    """给股票列表补充行业信息"""
    profiles = _load_profiles()
    if not profiles:
        return stocks
    for s in stocks:
        if not s.get("industry"):
            p = profiles.get(s.get("code", ""), {})
            if p.get("industry"):
                s["industry"] = p["industry"]
    return stocks


# ═══════════════════════════════════════════════════════
# Tool 1: query_market_overview
# ═══════════════════════════════════════════════════════

def query_market_overview(da: DataAccess) -> str:
    """全市场概览快照"""

    if da.is_online():
        health = da.api_get("/api/v1/health")
        factor_data = da.api_get("/api/v1/factor/weights")

        # 优先用带 cluster_id 的全量数据
        all_stocks = da.api_get("/api/v1/stocks/all")
        if all_stocks and all_stocks.get("results"):
            return _format_market_overview_online(all_stocks["results"], health, factor_data)

        # fallback: 用 snapshot 接口（无 cluster_id）
        snapshot_data = da.api_get("/api/v1/data/snapshot")
        if snapshot_data and snapshot_data.get("stocks"):
            return _format_market_overview_online(snapshot_data["stocks"], health, factor_data)

        return error_msg("NO_DATA", "无可用市场数据", "后端在线但暂无数据，请先运行 compute_terrain。")

    # 离线模式
    snapshot = da.get_latest_snapshot()
    clusters = da.get_latest_cluster_results()

    if snapshot.empty:
        return error_msg("NO_DATA", "无可用市场数据", "需先运行 compute_terrain 积累数据。")

    return _format_market_overview_offline(snapshot, clusters)


def _format_market_overview_online(stocks: list[dict], health: dict | None, factor_data: dict | None) -> str:
    profiles = _load_profiles()
    for s in stocks:
        if not s.get("industry"):
            p = profiles.get(s.get("code", ""), {})
            if p.get("industry"):
                s["industry"] = p["industry"]

    total = len(stocks)
    pct_values = [s.get("z_pct_chg", s.get("pct_chg", 0)) for s in stocks]
    up = sum(1 for v in pct_values if v and float(v) > 0)
    down = sum(1 for v in pct_values if v and float(v) < 0)
    flat = total - up - down
    avg_pct = sum(float(v) for v in pct_values if v) / total if total > 0 else 0

    lines = [
        f"## 全市场概览",
        f"",
        f"- 股票总数: **{total}**",
        f"- 上涨: {up} | 下跌: {down} | 平盘: {flat}",
        f"- 全市场平均涨跌幅: **{fmt_pct(avg_pct)}**",
        f"",
    ]

    # 聚类信息
    cluster_map: dict[int, list[dict]] = {}
    for s in stocks:
        cid = s.get("cluster_id", -1)
        cluster_map.setdefault(cid, []).append(s)

    if cluster_map:
        lines.append(f"### 聚类概览 ({len(cluster_map)} 个)")
        lines.append("")
        lines.append("聚类ID | 数量 | 平均涨跌幅 | 代表股票 Top 3")
        lines.append("--- | --- | --- | ---")
        for cid in sorted(cluster_map.keys()):
            members = cluster_map[cid]
            size = len(members)
            avg = sum(float(s.get("z_pct_chg", s.get("pct_chg", 0)) or 0) for s in members) / size if size > 0 else 0
            top3 = sorted(members, key=lambda x: abs(float(x.get("z_pct_chg", x.get("pct_chg", 0)) or 0)), reverse=True)[:3]
            top3_str = ", ".join(f"{s.get('name', s['code'])}" for s in top3)
            label = "噪声" if cid == -1 else str(cid)
            lines.append(f"{label} | {size} | {fmt_pct(avg)} | {top3_str}")
        lines.append("")

    # 涨幅/跌幅排行
    sorted_stocks = sorted(stocks, key=lambda s: float(s.get("z_pct_chg", s.get("pct_chg", 0)) or 0), reverse=True)
    lines.append("### 涨幅前 10")
    lines.append("")
    top10 = sorted_stocks[:10]
    lines.append(stock_table(top10, ["code", "name", "pct_chg", "industry", "cluster_id"]))
    lines.append("")
    lines.append("### 跌幅前 10")
    lines.append("")
    bottom10 = sorted_stocks[-10:][::-1]
    lines.append(stock_table(bottom10, ["code", "name", "pct_chg", "industry", "cluster_id"]))

    return "\n".join(lines)


def _format_market_overview_offline(snapshot: pd.DataFrame, clusters: pd.DataFrame) -> str:
    profiles = _load_profiles()
    total = len(snapshot)
    pct = pd.to_numeric(snapshot.get("pct_chg", pd.Series(dtype=float)), errors="coerce").fillna(0)
    up = int((pct > 0).sum())
    down = int((pct < 0).sum())
    flat = total - up - down
    avg_pct = float(pct.mean())

    lines = [
        offline_warning("query_market_overview", "无聚类质量评分"),
        "",
        f"## 全市场概览",
        f"",
        f"- 股票总数: **{total}**",
        f"- 上涨: {up} | 下跌: {down} | 平盘: {flat}",
        f"- 全市场平均涨跌幅: **{fmt_pct(avg_pct)}**",
        "",
    ]

    # 聚类（如果有）
    if not clusters.empty and "cluster_id" in clusters.columns:
        cluster_groups = clusters.groupby("cluster_id")
        lines.append(f"### 聚类概览 ({len(cluster_groups)} 个)")
        lines.append("")
        lines.append("聚类ID | 数量 | 代表股票 Top 3")
        lines.append("--- | --- | ---")
        for cid, grp in cluster_groups:
            names = grp["name"].head(3).tolist() if "name" in grp.columns else grp["code"].head(3).tolist()
            lines.append(f"{cid} | {len(grp)} | {', '.join(str(n) for n in names)}")
        lines.append("")

    # 涨跌排行
    snapshot_sorted = snapshot.copy()
    snapshot_sorted["_pct"] = pct
    snapshot_sorted = snapshot_sorted.sort_values("_pct", ascending=False)

    def _row_to_dict(row):
        d = {"code": str(row.get("code", "")), "name": str(row.get("name", "")), "pct_chg": row.get("pct_chg", 0)}
        p = profiles.get(d["code"], {})
        if p.get("industry"):
            d["industry"] = p["industry"]
        return d

    top10 = [_row_to_dict(row) for _, row in snapshot_sorted.head(10).iterrows()]
    bottom10 = [_row_to_dict(row) for _, row in snapshot_sorted.tail(10).iloc[::-1].iterrows()]

    lines.append("### 涨幅前 10")
    lines.append("")
    lines.append(stock_table(top10, ["code", "name", "pct_chg", "industry"]))
    lines.append("")
    lines.append("### 跌幅前 10")
    lines.append("")
    lines.append(stock_table(bottom10, ["code", "name", "pct_chg", "industry"]))

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# Tool 2: search_stocks
# ═══════════════════════════════════════════════════════

def search_stocks(da: DataAccess, query: str) -> str:
    """股票搜索（模糊匹配代码或名称）"""

    if da.is_online():
        result = da.api_get("/api/v1/stocks/search", params={"q": query})
        if result and "results" in result:
            stocks = result["results"][:20]
            if not stocks:
                return f"未找到匹配 \"{query}\" 的股票。"
            stocks = _enrich_industry(stocks)
            return f"搜索 \"{query}\" 匹配到 {len(stocks)} 只股票:\n\n" + stock_table(
                stocks, ["code", "name", "pct_chg", "industry", "cluster_id"]
            )

    # 离线
    q = query.replace("'", "''")
    df = da.db_query(
        f"SELECT * FROM stock_snapshot WHERE code LIKE '%{q}%' OR name LIKE '%{q}%' ORDER BY code LIMIT 20"
    )
    if df.empty:
        return f"未找到匹配 \"{query}\" 的股票。"

    profiles = _load_profiles()
    stocks = []
    for _, row in df.iterrows():
        s = {"code": str(row["code"]), "name": str(row.get("name", "")), "pct_chg": row.get("pct_chg", 0)}
        p = profiles.get(s["code"], {})
        if p.get("industry"):
            s["industry"] = p["industry"]
        stocks.append(s)

    return f"搜索 \"{query}\" 匹配到 {len(stocks)} 只股票:\n\n" + stock_table(
        stocks, ["code", "name", "pct_chg", "industry"]
    )


# ═══════════════════════════════════════════════════════
# Tool 3: query_cluster
# ═══════════════════════════════════════════════════════

def query_cluster(da: DataAccess, cluster_id: int) -> str:
    """查询指定聚类的完整信息"""

    if da.is_online():
        # 从搜索接口获取全部股票，然后按 cluster_id 过滤
        result = da.api_get("/api/v1/stocks/search", params={"q": ""})
        if result and "results" in result:
            all_stocks = result["results"]
            members = [s for s in all_stocks if s.get("cluster_id") == cluster_id]
            if not members:
                return error_msg("NOT_FOUND", f"聚类 #{cluster_id} 不存在", "使用 query_market_overview 查看全部聚类列表。")
            members = _enrich_industry(members)
            return _format_cluster_online(cluster_id, members)

    # 离线
    clusters = da.get_latest_cluster_results()
    if clusters.empty:
        return error_msg("NO_DATA", "无聚类数据", "需先运行 compute_terrain 积累数据。")

    members = clusters[clusters["cluster_id"] == cluster_id]
    if members.empty:
        return error_msg("NOT_FOUND", f"聚类 #{cluster_id} 不存在", "使用 query_market_overview 查看全部聚类列表。")

    return _format_cluster_offline(cluster_id, members, da)


def _format_cluster_online(cluster_id: int, members: list[dict]) -> str:
    size = len(members)
    pct_values = [float(s.get("z_pct_chg", s.get("pct_chg", 0)) or 0) for s in members]
    avg_pct = sum(pct_values) / size if size > 0 else 0

    # 行业分布
    industry_counter: dict[str, int] = {}
    for s in members:
        ind = s.get("industry", "")
        if ind:
            industry_counter[ind] = industry_counter.get(ind, 0) + 1
    top_industries = sorted(industry_counter.items(), key=lambda x: -x[1])[:5]

    lines = [
        f"## 聚类 #{cluster_id}",
        f"",
        f"- 成员数: **{size}**",
        f"- 平均涨跌幅: **{fmt_pct(avg_pct)}**",
    ]

    if top_industries:
        lines.append(f"- 行业分布 Top 5: {', '.join(f'{name}({count})' for name, count in top_industries)}")

    lines.append("")
    lines.append("### 成员股票")
    lines.append("")

    # 按涨跌幅排序
    sorted_members = sorted(members, key=lambda s: float(s.get("z_pct_chg", s.get("pct_chg", 0)) or 0), reverse=True)
    display = sorted_members[:50]
    cols = ["code", "name", "pct_chg", "industry"]
    if any(s.get("z_rise_prob") or s.get("rise_prob") for s in display):
        cols.append("rise_prob")
    lines.append(stock_table(display, cols))

    if size > 50:
        lines.append(f"\n(显示前 50，共 {size} 只)")

    return "\n".join(lines)


def _format_cluster_offline(cluster_id: int, members: pd.DataFrame, da: DataAccess) -> str:
    profiles = _load_profiles()
    snapshot = da.get_latest_snapshot()

    # 合并行情数据
    snap_map = {}
    if not snapshot.empty:
        for _, row in snapshot.iterrows():
            snap_map[str(row["code"])] = row

    size = len(members)
    stocks = []
    for _, row in members.iterrows():
        code = str(row["code"])
        snap = snap_map.get(code, {})
        s = {
            "code": code,
            "name": str(row.get("name", snap.get("name", ""))),
            "pct_chg": snap.get("pct_chg", 0) if isinstance(snap, dict) else getattr(snap, "pct_chg", 0),
        }
        p = profiles.get(code, {})
        if p.get("industry"):
            s["industry"] = p["industry"]
        stocks.append(s)

    lines = [
        offline_warning("query_cluster", "无特征画像/语义标签"),
        "",
        f"## 聚类 #{cluster_id}",
        f"",
        f"- 成员数: **{size}**",
        "",
        "### 成员股票",
        "",
        stock_table(stocks[:50], ["code", "name", "pct_chg", "industry"]),
    ]
    if size > 50:
        lines.append(f"\n(显示前 50，共 {size} 只)")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# Tool 4: query_stock
# ═══════════════════════════════════════════════════════

def query_stock(da: DataAccess, code: str) -> str:
    """单股全维度分析"""

    profiles = _load_profiles()
    profile = profiles.get(code, {})

    if da.is_online():
        # 优先从内存聚类结果搜索（含 cluster_id/rise_prob）
        result = da.api_get("/api/v1/stocks/search", params={"q": code})
        if result and result.get("results"):
            matches = [s for s in result["results"] if s.get("code") == code]
            if matches:
                return _format_stock_online(matches[0], profile, da)
        # fallback: 用 snapshot 接口
        stock = da.api_get(f"/api/v1/data/snapshot/{code}")
        if stock and "code" in stock:
            return _format_stock_online(stock, profile, da)
        return error_msg("NOT_FOUND", f"未找到股票 {code}", "可使用 search_stocks 搜索。")

    # 离线
    df = da.db_query("SELECT * FROM stock_snapshot WHERE code = ?", [code])
    if df.empty:
        return error_msg("NOT_FOUND", f"未找到股票 {code}", "可使用 search_stocks 搜索。")

    row = df.iloc[0]
    history = da.get_daily_history(code, 20)
    return _format_stock_offline(row, profile, history)


def _format_stock_online(stock: dict, profile: dict, da: DataAccess) -> str:
    code = stock["code"]
    name = stock.get("name", "")
    industry = stock.get("industry") or profile.get("industry", "")

    lines = [
        f"## {name} ({code})",
        f"",
    ]
    if industry:
        lines.append(f"- 行业: {industry}")

    pct = stock.get("z_pct_chg", stock.get("pct_chg", 0))
    lines.append(f"- 涨跌幅: **{fmt_pct(pct)}**")

    for key, label in [
        ("z_turnover_rate", "换手率"),
        ("z_volume", "成交量"),
        ("z_amount", "成交额"),
        ("z_pe_ttm", "PE(TTM)"),
        ("z_pb", "PB"),
    ]:
        val = stock.get(key)
        if val:
            if key in ("z_amount",):
                lines.append(f"- {label}: {fmt_number(val)}")
            elif key == "z_turnover_rate":
                lines.append(f"- {label}: {float(val):.2f}%")
            else:
                lines.append(f"- {label}: {float(val):.2f}")

    cid = stock.get("cluster_id")
    if cid is not None:
        lines.append(f"- 所属聚类: #{cid}" + (" (噪声)" if cid == -1 else ""))

    rise_prob = stock.get("z_rise_prob")
    if rise_prob is not None:
        # z_rise_prob 是减去 0.5 后的值，加回来得到原始概率
        prob = float(rise_prob) + 0.5
        lines.append(f"- 明日上涨概率: **{fmt_prob(prob)}**")

    # 关联股票
    related = stock.get("related_stocks", [])
    if related:
        lines.append("")
        lines.append("### 同簇关联 Top 5")
        lines.append("")
        lines.append(stock_table(related[:5], ["code", "name", "pct_chg", "industry"]))

    similar = stock.get("similar_stocks", [])
    if similar:
        lines.append("")
        lines.append("### 跨簇相似 Top 5")
        lines.append("")
        lines.append(stock_table(similar[:5], ["code", "name", "pct_chg", "industry"]))

    # 近 20 日历史
    history = da.get_daily_history(code, 20)
    if not history.empty:
        lines.append("")
        lines.append("### 近 20 日行情")
        lines.append("")
        lines.append("日期 | 收盘 | 涨跌幅 | 成交量 | 换手率")
        lines.append("--- | --- | --- | --- | ---")
        for _, row in history.iterrows():
            d = str(row.get("date", ""))
            c = f"{float(row.get('close', 0)):.2f}"
            p = fmt_pct(row.get("pct_chg"))
            v = fmt_number(row.get("volume"))
            t = f"{float(row.get('turnover_rate', 0)):.2f}%" if row.get("turnover_rate") else "N/A"
            lines.append(f"{d} | {c} | {p} | {v} | {t}")

    return "\n".join(lines)


def _format_stock_offline(row, profile: dict, history: pd.DataFrame) -> str:
    code = str(row.get("code", ""))
    name = str(row.get("name", ""))
    industry = profile.get("industry", "")

    lines = [
        offline_warning("query_stock", "无因子分解/预测概率/相似股票"),
        "",
        f"## {name} ({code})",
        "",
    ]
    if industry:
        lines.append(f"- 行业: {industry}")

    lines.append(f"- 价格: {float(row.get('price', 0)):.2f}")
    lines.append(f"- 涨跌幅: **{fmt_pct(row.get('pct_chg'))}**")

    for key, label in [
        ("turnover_rate", "换手率"), ("pe_ttm", "PE(TTM)"), ("pb", "PB"),
        ("total_mv", "总市值"), ("circ_mv", "流通市值"),
    ]:
        val = row.get(key)
        if val and float(val) != 0:
            if key in ("total_mv", "circ_mv"):
                lines.append(f"- {label}: {fmt_number(val)}")
            elif key == "turnover_rate":
                lines.append(f"- {label}: {float(val):.2f}%")
            else:
                lines.append(f"- {label}: {float(val):.2f}")

    if not history.empty:
        lines.append("")
        lines.append("### 近 20 日行情")
        lines.append("")
        lines.append("日期 | 收盘 | 涨跌幅 | 成交量 | 换手率")
        lines.append("--- | --- | --- | --- | ---")
        for _, r in history.iterrows():
            d = str(r.get("date", ""))
            c = f"{float(r.get('close', 0)):.2f}"
            p = fmt_pct(r.get("pct_chg"))
            v = fmt_number(r.get("volume"))
            t = f"{float(r.get('turnover_rate', 0)):.2f}%" if r.get("turnover_rate") else "N/A"
            lines.append(f"{d} | {c} | {p} | {v} | {t}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# Tool 5: query_factor_analysis
# ═══════════════════════════════════════════════════════

def query_factor_analysis(da: DataAccess, factor_name: str | None = None) -> str:
    """因子体系全景"""

    if da.is_online():
        result = da.api_get("/api/v1/factor/weights")
        if result:
            factors = result.get("factors", [])
            source = result.get("weight_source", "unknown")

            if factor_name:
                matched = [f for f in factors if f["name"] == factor_name]
                if not matched:
                    return error_msg("NOT_FOUND", f"因子 '{factor_name}' 不存在",
                                     f"可用因子: {', '.join(f['name'] for f in factors)}")
                f = matched[0]
                return (
                    f"## 因子: {f['name']}\n\n"
                    f"- 来源列: `{f['source_col']}`\n"
                    f"- 方向: {'正向(+)' if f['direction'] > 0 else '负向(-)'}\n"
                    f"- 分组: {f['group']}\n"
                    f"- 当前权重: {f['weight']:.4f} (来源: {source})\n"
                    f"- 默认权重: {f['default_weight']:.4f}\n"
                    f"- 描述: {f['desc']}\n"
                )

            lines = [
                f"## 因子体系 (13 因子)",
                f"",
                f"权重来源: **{source}**" + (" (ICIR自适应)" if source == "icir_adaptive" else " (默认权重)"),
                "",
                factor_table(factors),
            ]
            return "\n".join(lines)

    # 离线：从代码常量读取
    from quant_engine.predictor import FACTOR_DEFS

    if factor_name:
        matched = [f for f in FACTOR_DEFS if f.name == factor_name]
        if not matched:
            return error_msg("NOT_FOUND", f"因子 '{factor_name}' 不存在",
                             f"可用因子: {', '.join(f.name for f in FACTOR_DEFS)}")
        f = matched[0]
        return (
            f"## 因子: {f.name}\n\n"
            f"- 来源列: `{f.source_col}`\n"
            f"- 方向: {'正向(+)' if f.direction > 0 else '负向(-)'}\n"
            f"- 分组: {f.group}\n"
            f"- 默认权重: {f.default_weight:.4f}\n"
            f"- 描述: {f.desc}\n"
        )

    factors = [
        {
            "name": f.name, "direction": f.direction, "group": f.group,
            "weight": f.default_weight, "desc": f.desc,
        }
        for f in FACTOR_DEFS
    ]

    lines = [
        offline_warning("query_factor_analysis", "无 ICIR 自适应权重"),
        "",
        f"## 因子体系 (13 因子)",
        "",
        "权重来源: **默认权重**",
        "",
        factor_table(factors),
    ]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# Tool 6: find_similar_stocks
# ═══════════════════════════════════════════════════════

def find_similar_stocks(da: DataAccess, code: str, top_k: int = 10) -> str:
    """跨簇相似股票搜索"""

    if da.is_online():
        result = da.api_get("/api/v1/stocks/search", params={"q": code})
        if result and result.get("results"):
            matches = [s for s in result["results"] if s.get("code") == code]
            if matches:
                stock = matches[0]
                similar = stock.get("similar_stocks", [])
                related = stock.get("related_stocks", [])
                all_similar = similar + [r for r in related if r.get("code") not in {s.get("code") for s in similar}]
                all_similar = _enrich_industry(all_similar[:top_k])

                if not all_similar:
                    return f"股票 {code} 暂无相似股票数据。需先运行 compute_terrain。"

                name = stock.get("name", code)
                return (
                    f"## {name} ({code}) 的相似股票 (Top {len(all_similar)})\n\n"
                    + stock_table(all_similar, ["code", "name", "pct_chg", "industry"])
                )

    # 离线：尝试用 BGE 嵌入做近似搜索
    try:
        return _find_similar_offline(da, code, top_k)
    except Exception as e:
        logger.warning(f"离线相似搜索失败: {e}")
        return error_msg("NO_DATA", f"无法搜索 {code} 的相似股票", "需后端在线或存在 stock_embeddings.npz 文件。")


def _find_similar_offline(da: DataAccess, code: str, top_k: int) -> str:
    import numpy as np

    emb_path = Path(__file__).resolve().parent.parent.parent / "data" / "precomputed" / "stock_embeddings.npz"
    if not emb_path.exists():
        return error_msg("NO_DATA", "无 BGE 嵌入数据", "需后端在线模式获取完整相似度数据。")

    data = np.load(emb_path, allow_pickle=True)
    codes = list(data.get("codes", []))
    embeddings = data.get("embeddings")

    if code not in codes:
        return error_msg("NOT_FOUND", f"未找到股票 {code}", "可使用 search_stocks 搜索。")

    idx = codes.index(code)
    target = embeddings[idx]

    # 余弦相似度
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normalized = embeddings / norms
    target_norm = target / (np.linalg.norm(target) or 1)
    similarities = normalized @ target_norm

    # 排序
    top_indices = np.argsort(similarities)[::-1][1:top_k + 1]

    profiles = _load_profiles()
    snapshot = da.get_latest_snapshot()
    snap_map = {}
    if not snapshot.empty:
        for _, row in snapshot.iterrows():
            snap_map[str(row["code"])] = row

    stocks = []
    for i in top_indices:
        c = codes[i]
        snap = snap_map.get(c, {})
        p = profiles.get(c, {})
        s = {
            "code": c,
            "name": p.get("name", str(snap.get("name", c)) if isinstance(snap, dict) else getattr(snap, "name", c)),
            "pct_chg": snap.get("pct_chg", 0) if isinstance(snap, dict) else getattr(snap, "pct_chg", 0),
            "industry": p.get("industry", ""),
        }
        stocks.append(s)

    name = profiles.get(code, {}).get("name", code)
    return (
        offline_warning("find_similar_stocks", "仅基于语义嵌入，无财务特征") + "\n\n"
        f"## {name} ({code}) 的相似股票 (Top {len(stocks)})\n\n"
        + stock_table(stocks, ["code", "name", "pct_chg", "industry"])
    )


# ═══════════════════════════════════════════════════════
# Tool 7: query_history
# ═══════════════════════════════════════════════════════

def query_history(da: DataAccess, code: str, days: int = 60) -> str:
    """历史行情数据"""

    history = da.get_daily_history(code, days)
    if history.empty:
        return error_msg("NO_DATA", f"股票 {code} 无本地历史数据", "需先运行 compute_terrain 积累数据。")

    profiles = _load_profiles()
    name = profiles.get(code, {}).get("name", code)

    lines = [
        f"## {name} ({code}) 近 {len(history)} 日行情",
        "",
        "日期 | 开盘 | 最高 | 最低 | 收盘 | 成交量 | 成交额 | 涨跌幅 | 换手率",
        "--- | --- | --- | --- | --- | --- | --- | --- | ---",
    ]

    for _, row in history.iterrows():
        d = str(row.get("date", ""))
        o = f"{float(row.get('open', 0)):.2f}"
        h = f"{float(row.get('high', 0)):.2f}"
        lo = f"{float(row.get('low', 0)):.2f}"
        c = f"{float(row.get('close', 0)):.2f}"
        v = fmt_number(row.get("volume"))
        a = fmt_number(row.get("amount"))
        p = fmt_pct(row.get("pct_chg"))
        t = f"{float(row.get('turnover_rate', 0)):.2f}%" if row.get("turnover_rate") else "N/A"
        lines.append(f"{d} | {o} | {h} | {lo} | {c} | {v} | {a} | {p} | {t}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# Tool 8: run_screen
# ═══════════════════════════════════════════════════════

def run_screen(
    da: DataAccess,
    filters: dict,
    sort_by: str = "pct_chg",
    sort_desc: bool = True,
    limit: int = 20,
) -> str:
    """条件选股筛选"""

    limit = min(limit, 50)

    if da.is_online():
        result = da.api_get("/api/v1/stocks/search", params={"q": ""})
        if result and result.get("results"):
            stocks = result["results"]
            filtered = _apply_filters(stocks, filters, is_online=True)
            if not filtered:
                return error_msg("NO_DATA", "无满足条件的股票", f"当前筛选条件: {filters}")

            # 排序
            def _sort_key(s):
                val = s.get(f"z_{sort_by}", s.get(sort_by, 0))
                return float(val) if val else 0
            filtered.sort(key=_sort_key, reverse=sort_desc)
            display = _enrich_industry(filtered[:limit])

            cols = ["code", "name", "pct_chg", "industry", "cluster_id"]
            if any(s.get("z_rise_prob") or s.get("rise_prob") for s in display):
                cols.append("rise_prob")

            return (
                f"## 选股结果 ({len(filtered)} 只满足条件，显示 Top {len(display)})\n\n"
                f"筛选条件: {filters}\n"
                f"排序: {sort_by} {'↓' if sort_desc else '↑'}\n\n"
                + stock_table(display, cols)
            )

    # 离线
    snapshot = da.get_latest_snapshot()
    if snapshot.empty:
        return error_msg("NO_DATA", "无可用市场数据", "需先运行 compute_terrain 积累数据。")

    profiles = _load_profiles()
    stocks = []
    for _, row in snapshot.iterrows():
        code = str(row["code"])
        s = {
            "code": code,
            "name": str(row.get("name", "")),
            "pct_chg": row.get("pct_chg", 0),
            "turnover_rate": row.get("turnover_rate", 0),
            "volume": row.get("volume", 0),
            "amount": row.get("amount", 0),
            "pe_ttm": row.get("pe_ttm", 0),
            "pb": row.get("pb", 0),
            "total_mv": row.get("total_mv", 0),
            "circ_mv": row.get("circ_mv", 0),
            "price": row.get("price", 0),
        }
        p = profiles.get(code, {})
        if p.get("industry"):
            s["industry"] = p["industry"]
        stocks.append(s)

    filtered = _apply_filters(stocks, filters, is_online=False)
    if not filtered:
        return error_msg("NO_DATA", "无满足条件的股票", f"当前筛选条件: {filters}")

    def _sort_key(s):
        return float(s.get(sort_by, 0) or 0)
    filtered.sort(key=_sort_key, reverse=sort_desc)
    display = filtered[:limit]

    prefix = offline_warning("run_screen", "缺少 rise_prob/cluster_id") + "\n\n" if True else ""
    return (
        prefix
        + f"## 选股结果 ({len(filtered)} 只满足条件，显示 Top {len(display)})\n\n"
        f"筛选条件: {filters}\n"
        f"排序: {sort_by} {'↓' if sort_desc else '↑'}\n\n"
        + stock_table(display, ["code", "name", "pct_chg", "industry", "pe_ttm", "pb"])
    )


def _apply_filters(stocks: list[dict], filters: dict, is_online: bool = True) -> list[dict]:
    """应用 Filter DSL"""
    result = []
    for s in stocks:
        match = True
        for key, condition in filters.items():
            val = s.get(f"z_{key}", s.get(key)) if is_online else s.get(key)
            if val is None:
                match = False
                break

            try:
                val = float(val)
            except (TypeError, ValueError):
                val_str = str(val)

            if isinstance(condition, dict):
                if "min" in condition and val < condition["min"]:
                    match = False
                    break
                if "max" in condition and val > condition["max"]:
                    match = False
                    break
                if "in" in condition and val not in condition["in"] and int(val) not in condition["in"]:
                    match = False
                    break
            else:
                # 精确匹配
                if isinstance(condition, str):
                    if str(val_str) != condition:
                        match = False
                        break
                elif val != condition and int(val) != condition:
                    match = False
                    break

        if match:
            result.append(s)

    return result


# ═══════════════════════════════════════════════════════
# Tool 9: run_backtest
# ═══════════════════════════════════════════════════════

def run_backtest(
    da: DataAccess,
    rolling_window: int = 20,
    auto_inject: bool = False,
) -> str:
    """触发因子 IC 回测"""

    if da.is_online():
        result = da.api_post(
            "/api/v1/factor/backtest",
            params={"rolling_window": rolling_window, "auto_inject": auto_inject},
        )
        if result:
            if result.get("_error") == "BUSY":
                return error_msg("BUSY", result["_message"], "稍后重试。")

            return _format_backtest_result(result, auto_inject)

    # 离线：本地计算
    try:
        from quant_engine.factor_backtest import FactorBacktester

        daily_snapshots = da.get_snapshot_daily_range(30)
        if len(daily_snapshots) < 3:
            return error_msg("NO_DATA", f"历史快照不足（{len(daily_snapshots)} 天），至少需要 3 天",
                             "需先多次运行 compute_terrain 积累数据。")

        backtester = FactorBacktester(rolling_window=rolling_window)
        bt_result = backtester.run_backtest(daily_snapshots)

        report = {
            "backtest_days": bt_result.backtest_days,
            "total_stocks_avg": bt_result.total_stocks_avg,
            "computation_time_ms": round(bt_result.computation_time_ms, 0),
            "factors": [],
            "icir_weights": bt_result.icir_weights,
            "weights_injected": False,
        }
        for name, r in bt_result.factor_reports.items():
            report["factors"].append({
                "name": name,
                "ic_mean": r.ic_mean,
                "ic_std": r.ic_std,
                "icir": r.icir,
                "ic_positive_rate": r.ic_positive_rate,
                "t_stat": r.t_stat,
                "p_value": r.p_value,
            })

        return _format_backtest_result(report, auto_inject)

    except Exception as e:
        return error_msg("NO_DATA", f"离线回测失败: {e}", "请确保有足够的历史快照数据。")


def _format_backtest_result(result: dict, auto_inject: bool) -> str:
    days = result.get("backtest_days", 0)
    avg_stocks = result.get("total_stocks_avg", 0)
    elapsed = result.get("computation_time_ms", 0)
    factors = result.get("factors", [])
    weights = result.get("icir_weights", {})
    injected = result.get("weights_injected", False)

    lines = [
        f"## 因子 IC 回测结果",
        "",
        f"- 回测天数: {days}",
        f"- 平均股票数: {avg_stocks}",
        f"- 计算耗时: {elapsed:.0f}ms",
        f"- 权重注入: {'是' if injected else '否'}" + (" (auto_inject=False)" if not auto_inject else ""),
        "",
        "### 因子 IC 统计",
        "",
        "因子 | IC均值 | IC标准差 | ICIR | IC>0% | t统计量 | p值",
        "--- | --- | --- | --- | --- | --- | ---",
    ]

    for f in factors:
        lines.append(
            f"{f['name']} | {f['ic_mean']:.4f} | {f['ic_std']:.4f} | "
            f"{f['icir']:.4f} | {f['ic_positive_rate']:.1%} | "
            f"{f['t_stat']:.4f} | {f['p_value']:.6f}"
        )

    if weights:
        lines.append("")
        lines.append("### ICIR 自适应权重")
        lines.append("")
        lines.append("因子 | 权重")
        lines.append("--- | ---")
        for name, w in sorted(weights.items(), key=lambda x: abs(x[1]), reverse=True):
            lines.append(f"{name} | {w:.4f}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# Tool 10: compute_terrain
# ═══════════════════════════════════════════════════════

def compute_terrain(
    da: DataAccess,
    z_metric: str = "pct_chg",
    radius_scale: float = 2.0,
) -> str:
    """触发全量地形计算（仅在线模式）"""

    if not da.is_online():
        return error_msg("OFFLINE", "后端未运行，无法触发计算", "请先启动 engine: `python main.py`")

    result = da.api_post_sse(
        "/api/v1/terrain/compute",
        params={"z_metric": z_metric, "radius_scale": radius_scale},
    )

    if result is None:
        return error_msg("OFFLINE", "后端通信失败", "请确认 engine 已启动: `python main.py`")

    if result.get("_error") == "BUSY":
        return error_msg("BUSY", result["_message"], "稍后重试。")

    if result.get("_error"):
        return error_msg("API_ERROR", result.get("_message", "未知错误"), "检查后端日志。")

    stock_count = result.get("stock_count", 0)
    cluster_count = result.get("cluster_count", 0)
    elapsed = result.get("computation_time_ms", 0)
    quality = result.get("cluster_quality", {})

    lines = [
        f"## 地形计算完成",
        "",
        f"- 股票数: {stock_count}",
        f"- 聚类数: {cluster_count}",
        f"- Z 轴指标: {z_metric}",
        f"- 耗时: {elapsed:.0f}ms",
    ]

    if quality:
        sil = quality.get("silhouette_score", 0)
        ch = quality.get("calinski_harabasz", 0)
        noise = quality.get("noise_ratio", 0)
        lines.append(f"- 聚类质量: Silhouette={sil:.4f}, CH={ch:.1f}, 噪声率={noise:.1%}")

    return "\n".join(lines)


# ─── QuantEngine Tools ──────────────────────────────

def get_technical_indicators(da: "DataAccess", code: str) -> str:
    """获取技术指标"""
    import json

    # 在线时走 REST API，避免 DuckDB 连接冲突
    if da.is_online():
        data = da.api_get(f"/api/v1/quant/indicators/{code}")
        if data:
            return json.dumps(data, ensure_ascii=False, indent=2)

    # 离线降级：本地计算
    try:
        from quant_engine import get_quant_engine
    except ImportError:
        return json.dumps({"error": "QuantEngine 未安装"}, ensure_ascii=False)

    daily = da.get_daily_history(code, days=90)
    if daily is None or daily.empty:
        return json.dumps({"error": f"无 {code} 日线数据"}, ensure_ascii=False)

    qe = get_quant_engine()
    indicators = qe.compute_indicators(daily)
    return json.dumps({"code": code, "indicators": indicators}, ensure_ascii=False, indent=2)


def get_factor_scores(da: "DataAccess", code: str) -> str:
    """获取多因子评分"""
    import json

    if not da.is_online():
        return json.dumps({"error": "后端未在线，无法获取因子评分"}, ensure_ascii=False)

    stock_data = da.get_stock_detail(code)
    if not stock_data:
        return json.dumps({"error": f"无 {code} 数据"}, ensure_ascii=False)

    weights_data = da.api_get("/api/v1/quant/factor/weights")
    defs_data = da.api_get("/api/v1/quant/factor/defs")
    if not weights_data or not defs_data:
        return json.dumps({"error": "无法获取因子定义"}, ensure_ascii=False)

    weight_map = {f["name"]: f["weight"] for f in weights_data.get("factors", [])}
    source = weights_data.get("weight_source", "default")

    scores = {}
    for fdef in defs_data:
        col = fdef.get("source_col", "")
        if col.startswith("_"):
            continue
        val = stock_data.get(col)
        if val is not None:
            scores[fdef["name"]] = {
                "value": round(float(val), 4),
                "direction": fdef.get("direction", 1),
                "weight": weight_map.get(fdef["name"], fdef.get("default_weight", 0)),
                "desc": fdef.get("desc", ""),
            }
    return json.dumps({
        "code": code,
        "weight_source": source,
        "factor_scores": scores,
    }, ensure_ascii=False, indent=2)


def submit_analysis(code: str, depth: str = "standard") -> str:
    """触发分析（同步返回状态，实际分析通过 REST API SSE 进行）"""
    import json
    return json.dumps({
        "status": "请通过 POST /api/v1/analysis 触发分析",
        "hint": f"curl -X POST http://localhost:8000/api/v1/analysis -H 'Content-Type: application/json' -d '{{\"trigger_type\":\"user\",\"target\":\"{code}\",\"target_type\":\"stock\",\"depth\":\"{depth}\"}}'",
    }, ensure_ascii=False, indent=2)


def get_analysis_history(code: str, limit: int = 5) -> str:
    """查询历史分析报告 — Phase 1: 返回空（持久化在 Phase 2 实现）"""
    import json
    return json.dumps({
        "code": code,
        "history": [],
        "note": "历史分析报告持久化将在 Phase 2 实现",
    }, ensure_ascii=False, indent=2)


def get_signal_history(da: "DataAccess", code: str, days: int = 30) -> str:
    """查询历史量化信号 — Phase 1: 返回空（信号持久化在 Phase 2 实现）"""
    import json
    return json.dumps({
        "code": code,
        "signals": [],
        "note": "历史信号记录将在 Phase 2 QuantEngine DuckDB 持久化后实现",
    }, ensure_ascii=False, indent=2)


# ─── InfoEngine Tools ──────────────────────────────

def _run_async(coro):
    """安全运行 async 协程 — 处理 MCP server 已有事件循环的情况"""
    import asyncio
    try:
        asyncio.get_running_loop()
        # 已在事件循环中（MCP stdio transport），用新线程运行
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=60)
    except RuntimeError:
        # 无运行中的事件循环，直接 asyncio.run
        return asyncio.run(coro)


def get_news(da: "DataAccess", code: str, limit: int = 20) -> str:
    """获取个股新闻 + 情感分析"""
    try:
        from info_engine import get_info_engine
        ie = get_info_engine()
        news = _run_async(ie.get_news(code, limit))

        if not news:
            return json.dumps({"code": code, "news": [], "note": "暂无新闻数据"}, ensure_ascii=False)

        summary = {"positive": 0, "negative": 0, "neutral": 0}
        news_list = []
        for n in news:
            if n.sentiment in summary:
                summary[n.sentiment] += 1
            news_list.append(n.model_dump())

        return json.dumps({
            "code": code,
            "news": news_list,
            "sentiment_summary": summary,
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"新闻获取失败: {e}"}, ensure_ascii=False)


def get_announcements(da: "DataAccess", code: str, limit: int = 10) -> str:
    """获取公司公告 + 情感分析"""
    try:
        from info_engine import get_info_engine
        ie = get_info_engine()
        anns = _run_async(ie.get_announcements(code, limit))

        if not anns:
            return json.dumps({"code": code, "announcements": [], "note": "暂无公告数据"}, ensure_ascii=False)

        return json.dumps({
            "code": code,
            "announcements": [a.model_dump() for a in anns],
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"公告获取失败: {e}"}, ensure_ascii=False)


def assess_event_impact(da: "DataAccess", code: str, event_desc: str) -> str:
    """评估事件对个股的影响"""
    try:
        from info_engine import get_info_engine
        ie = get_info_engine()
        impact = _run_async(ie.assess_event_impact(code, event_desc))
        return json.dumps(impact.model_dump(), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"事件评估失败: {e}"}, ensure_ascii=False)


# TODO Phase 4: full_analysis 组合工具（预留，本次不实现）
# def full_analysis(da: DataAccess, code: str) -> str:
#     """并行调用三引擎数据聚合，返回结构化 Markdown 报告（不调 LLM，推理留给 MCP 调用方）"""
#     pass


# ─── Debate Tools ──────────────────────────────────

def _get_debate_record(da: "DataAccess", debate_id: str) -> dict | None:
    """从 DuckDB 读取辩论记录"""
    try:
        df = da.db_query(
            "SELECT * FROM shared.debate_records WHERE id = ?", [debate_id]
        )
        if df.empty:
            return None
        return df.iloc[0].to_dict()
    except Exception:
        return None


async def start_debate_async(da: "DataAccess", code: str, max_rounds: int, ctx=None) -> str:
    """发起专家辩论 — 异步消费 SSE 流，通过 MCP notification 实时推送"""
    import httpx

    if not da.is_online():
        return json.dumps({
            "error": "后端未运行，无法发起辩论",
            "hint": "请先启动 engine: `cd engine && python main.py`",
        }, ensure_ascii=False, indent=2)

    ROLE_NAMES = {
        "bull_expert": "多头专家", "bear_expert": "空头专家",
        "retail_investor": "散户代表", "smart_money": "主力代表",
    }

    try:
        lines = []
        debate_id = None

        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
            async with client.stream(
                "POST", f"{da._api_base}/api/v1/debate",
                json={"code": code, "max_rounds": max_rounds},
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

                        if event_type == "debate_start":
                            debate_id = data.get("debate_id")
                            lines.append(f"# 专家辩论: {code}")
                            lines.append(f"debate_id: `{debate_id}` | max_rounds: {data.get('max_rounds')}")
                            lines.append("")

                        elif event_type == "debate_round_start":
                            rd = data.get("round", 0)
                            is_final = data.get("is_final", False)
                            lines.append("---")
                            lines.append(f"## Round {rd}" + (" (最终轮)" if is_final else ""))
                            lines.append("")

                        elif event_type == "debate_token":
                            role = data.get("role", "")
                            role_cn = ROLE_NAMES.get(role, role)
                            tokens_text = data.get("tokens", "")
                            if ctx:
                                await ctx.log("info", f"[{role_cn}] {tokens_text}")

                        elif event_type == "debate_entry_complete":
                            role = data.get("role", "")
                            role_cn = ROLE_NAMES.get(role, role)
                            stance = data.get("stance")
                            conf = data.get("confidence", 0)
                            arg = data.get("argument", "")
                            challenges = data.get("challenges", [])
                            sentiment = data.get("retail_sentiment_score")

                            header = f"### {role_cn}"
                            if stance:
                                header += f" [{stance}]"
                            header += f" (confidence={conf:.2f})"
                            if sentiment is not None:
                                header += f" | 情绪={sentiment:+.2f}"
                            lines.append(header)
                            lines.append("")
                            if arg:
                                lines.append(arg)
                                lines.append("")
                            if challenges:
                                lines.append("**质疑:**")
                                for i, c in enumerate(challenges, 1):
                                    lines.append(f"{i}. {c}")
                                lines.append("")
                            if ctx:
                                await ctx.log("info", f"✅ {role_cn} 发言完毕 (confidence={conf:.2f})")

                        elif event_type == "data_request_start":
                            if ctx:
                                await ctx.log("info",
                                    f"📊 [{ROLE_NAMES.get(data.get('requested_by',''), data.get('requested_by',''))}] "
                                    f"→ {data.get('engine')}.{data.get('action')}()")
                            lines.append(f"> 📊 数据请求: {data.get('engine')}.{data.get('action')} "
                                        f"(by {ROLE_NAMES.get(data.get('requested_by',''), data.get('requested_by',''))})")

                        elif event_type == "data_request_done":
                            status_icon = "✅" if data.get("status") == "done" else "❌"
                            if ctx:
                                await ctx.log("info",
                                    f"{status_icon} {data.get('action')} ({data.get('duration_ms', 0)}ms)")
                            lines.append(f"> {status_icon} {data.get('action')} "
                                        f"({data.get('duration_ms', 0)}ms): {data.get('result_summary', '')}")

                        elif event_type == "data_batch_complete":
                            if ctx:
                                await ctx.log("info",
                                    f"📋 数据请求完毕: {data.get('success')}/{data.get('total')} 成功")
                            lines.append("")

                        elif event_type == "judge_token":
                            tokens_text = data.get("tokens", "")
                            if ctx:
                                await ctx.log("info", f"[裁判] {tokens_text}")

                        elif event_type == "debate_end":
                            reason = data.get("reason", "")
                            rounds = data.get("rounds_completed", 0)
                            lines.append("---")
                            lines.append(f"辩论结束 | 完成 {rounds} 轮 | 终止原因: {reason}")
                            lines.append("")

                        elif event_type == "judge_verdict":
                            lines.append("---")
                            lines.append("# 裁判裁决")
                            lines.append("")
                            lines.append(data.get("summary", ""))
                            lines.append("")
                            signal = data.get("signal")
                            score = data.get("score")
                            if signal:
                                score_str = f" (score={score:.2f})" if score is not None else ""
                                lines.append(f"**信号: {signal}{score_str}**")
                                lines.append("")
                            lines.append(f"**多头核心论点:** {data.get('bull_core_thesis', '')}")
                            lines.append("")
                            lines.append(f"**空头核心论点:** {data.get('bear_core_thesis', '')}")
                            lines.append("")
                            lines.append(f"**散户情绪参考:** {data.get('retail_sentiment_note', '')}")
                            lines.append("")
                            lines.append(f"**主力资金动向:** {data.get('smart_money_note', '')}")
                            lines.append("")
                            lines.append(f"**辩论质量:** {data.get('debate_quality', '')}")
                            lines.append("")
                            warnings = data.get("risk_warnings", [])
                            if warnings:
                                lines.append("**风险提示:**")
                                for i, w in enumerate(warnings, 1):
                                    lines.append(f"{i}. {w}")
                                lines.append("")
                            key_args = data.get("key_arguments", [])
                            if key_args:
                                lines.append("**关键论据:**")
                                for i, a in enumerate(key_args, 1):
                                    lines.append(f"{i}. {a}")

                        elif event_type == "error":
                            return json.dumps({"error": data.get("message", "辩论失败")}, ensure_ascii=False)

                        event_type = None
                        data_buf = ""

        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 503:
            return json.dumps({"error": "LLM 未配置，请先在 .env 中设置 API Key"}, ensure_ascii=False)
        return json.dumps({"error": f"辩论请求失败: {e}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"辩论失败: {e}"}, ensure_ascii=False)


def get_debate_status(da: "DataAccess", debate_id: str) -> str:
    """查询辩论进度"""
    record = _get_debate_record(da, debate_id)
    if not record:
        return json.dumps({"error": f"未找到辩论记录: {debate_id}"}, ensure_ascii=False)

    bb_json = record.get("blackboard_json")
    status_info = {
        "debate_id": debate_id,
        "target": record.get("target"),
        "max_rounds": record.get("max_rounds"),
        "rounds_completed": record.get("rounds_completed"),
        "termination_reason": record.get("termination_reason"),
        "created_at": str(record.get("created_at", "")),
        "completed_at": str(record.get("completed_at", "")),
    }

    if bb_json:
        try:
            bb = json.loads(bb_json)
            status_info["status"] = bb.get("status", "unknown")
            status_info["bull_conceded"] = bb.get("bull_conceded", False)
            status_info["bear_conceded"] = bb.get("bear_conceded", False)
        except json.JSONDecodeError:
            status_info["status"] = "unknown"

    return json.dumps(status_info, ensure_ascii=False, indent=2)


def get_debate_transcript(
    da: "DataAccess", debate_id: str,
    round: int | None = None, role: str | None = None,
) -> str:
    """获取辩论记录，支持按轮次和角色过滤"""
    record = _get_debate_record(da, debate_id)
    if not record:
        return json.dumps({"error": f"未找到辩论记录: {debate_id}"}, ensure_ascii=False)

    bb_json = record.get("blackboard_json")
    if not bb_json:
        return json.dumps({"error": "辩论记录无 Blackboard 数据"}, ensure_ascii=False)

    try:
        bb = json.loads(bb_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "Blackboard JSON 解析失败"}, ensure_ascii=False)

    transcript = bb.get("transcript", [])

    # 过滤
    if round is not None:
        transcript = [e for e in transcript if e.get("round") == round]
    if role is not None:
        transcript = [e for e in transcript if e.get("role") == role]

    return json.dumps({
        "debate_id": debate_id,
        "target": record.get("target"),
        "total_entries": len(transcript),
        "transcript": transcript,
    }, ensure_ascii=False, indent=2)


def get_judge_verdict(da: "DataAccess", debate_id: str) -> str:
    """获取裁判最终总结"""
    record = _get_debate_record(da, debate_id)
    if not record:
        return json.dumps({"error": f"未找到辩论记录: {debate_id}"}, ensure_ascii=False)

    verdict_json = record.get("judge_verdict_json")
    if not verdict_json:
        return json.dumps({
            "error": "辩论尚未完成或无裁判总结",
            "debate_id": debate_id,
        }, ensure_ascii=False)

    try:
        verdict = json.loads(verdict_json)
        return json.dumps(verdict, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        return json.dumps({"error": "JudgeVerdict JSON 解析失败"}, ensure_ascii=False)
