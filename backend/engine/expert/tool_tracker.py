"""工具使用反馈追踪器 — 借鉴 OpenClaw TOOLS 层技能记忆

记录每次对话的工具使用模式和结果，供 think 步骤学习参考。
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime

import duckdb
from loguru import logger


def classify_query(message: str) -> str:
    """对用户消息做简单查询类型分类（关键词规则，不调 LLM）"""
    # 有序列表：特征性强的类型优先匹配，避免"板块怎么样"误匹配到个股分析
    ordered_patterns = [
        ("板块行业", [r"板块", r"行业", r"产业", r"轮动", r"龙头"]),
        ("技术面", [r"技术", r"MACD", r"RSI", r"KDJ", r"均线", r"支撑", r"阻力",
                   r"金叉", r"死叉", r"布林"]),
        ("消息面", [r"新闻", r"公告", r"消息", r"利好", r"利空", r"为什么涨", r"为什么跌"]),
        ("选股推荐", [r"推荐", r"选股", r"买什么", r"配置", r"好股", r"有什么好"]),
        ("个股分析", [r"分析", r"怎么样", r"值不值", r"怎么看", r"能不能买", r"持仓"]),
    ]
    for qtype, kws in ordered_patterns:
        if any(re.search(kw, message, re.IGNORECASE) for kw in kws):
            return qtype
    return "闲聊"


class ToolOutcomeTracker:
    """工具使用结果追踪器

    存储到 DuckDB expert.tool_outcomes 表，统计后注入 think prompt。
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._init_table()

    def _get_db(self):
        return duckdb.connect(self._db_path)

    def _init_table(self):
        con = None
        try:
            con = self._get_db()
            con.execute("CREATE SCHEMA IF NOT EXISTS expert")
            con.execute("""
                CREATE TABLE IF NOT EXISTS expert.tool_outcomes (
                    id VARCHAR PRIMARY KEY,
                    query_type VARCHAR NOT NULL,
                    tools_used VARCHAR NOT NULL,
                    success BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        except Exception as e:
            logger.warning(f"tool_outcomes 表初始化失败: {e}")
        finally:
            if con:
                con.close()

    def record(
        self,
        query_type: str,
        tools_used: list[str],
        success: bool,
    ) -> None:
        """记录一次工具使用结果"""
        con = None
        try:
            con = self._get_db()
            con.execute(
                "INSERT INTO expert.tool_outcomes (id, query_type, tools_used, success, created_at) "
                "VALUES (?,?,?,?,?)",
                [str(uuid.uuid4()), query_type,
                 json.dumps(tools_used, ensure_ascii=False),
                 success, datetime.now()],
            )
        except Exception as e:
            logger.warning(f"记录工具使用失败: {e}")
        finally:
            if con:
                con.close()

    def get_recent_stats(self, days: int = 7) -> list[dict]:
        """获取最近 N 天的工具使用统计（按 query_type 分组）"""
        con = None
        try:
            con = self._get_db()
            # DuckDB 的 INTERVAL 不支持参数化绑定，用 f-string（days 是 int，安全）
            rows = con.execute(f"""
                SELECT query_type,
                       tools_used,
                       COUNT(*) as cnt,
                       SUM(CASE WHEN success THEN 1 ELSE 0 END) as success_cnt
                FROM expert.tool_outcomes
                WHERE created_at > CURRENT_TIMESTAMP - INTERVAL '{int(days)}' DAY
                GROUP BY query_type, tools_used
                ORDER BY cnt DESC
                LIMIT 20
            """).fetchall()
            return [
                {"query_type": r[0], "tools_used": r[1],
                 "count": r[2], "success_count": r[3]}
                for r in rows
            ]
        except Exception as e:
            logger.debug(f"获取工具统计失败: {e}")
            return []
        finally:
            if con:
                con.close()

    def format_experience_prompt(self, days: int = 7) -> str:
        """格式化近期工具使用经验，供注入 think prompt"""
        stats = self.get_recent_stats(days)
        if not stats:
            return ""
        lines = ["## 近期工具使用经验（供参考）"]
        for s in stats[:10]:
            tools = s["tools_used"]
            rate = s["success_count"] / s["count"] * 100 if s["count"] else 0
            lines.append(
                f"- \"{s['query_type']}\"类问题：使用 {tools}，成功率 {rate:.0f}%（{s['count']}次）"
            )
        return "\n".join(lines)
