import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))


@pytest.mark.parametrize(
    ("method_name", "frame", "query", "expected"),
    [
        (
            "save_daily",
            pd.DataFrame(
                [
                    {
                        "code": "600519",
                        "date": "2026-03-27",
                        "open": 1800.0,
                        "high": 1810.0,
                        "low": 1790.0,
                        "close": 1805.0,
                        "volume": 12345,
                        "amount": 2.2e7,
                        "pct_chg": 1.2,
                        "turnover_rate": 0.8,
                    }
                ]
            ),
            "SELECT code, close FROM stock_daily",
            [("600519", 1805.0)],
        ),
        (
            "save_features",
            pd.DataFrame(
                [
                    {
                        "code": "600519",
                        "date": "2026-03-27",
                        "pe_ttm": 30.5,
                        "pb": 9.2,
                        "roe": 0.21,
                        "roa": 0.12,
                        "gross_margin": 0.91,
                        "net_margin": 0.52,
                        "revenue_yoy": 0.08,
                        "profit_yoy": 0.11,
                        "total_mv": 2.2e12,
                        "circ_mv": 1.8e12,
                        "volatility_20d": 0.13,
                        "volatility_60d": 0.19,
                        "beta": 0.72,
                        "rsi_14": 56.3,
                        "ma_deviation_20": 0.04,
                        "ma_deviation_60": 0.07,
                        "momentum_20d": 0.09,
                        "turnover_rate": 0.8,
                        "volume_ratio": 1.1,
                    }
                ]
            ),
            "SELECT code, pe_ttm FROM stock_features",
            [("600519", 30.5)],
        ),
        (
            "save_cluster_results",
            pd.DataFrame(
                [
                    {
                        "date": "2026-03-27",
                        "code": "600519",
                        "name": "贵州茅台",
                        "cluster_id": 1,
                        "x": 0.1,
                        "y": 0.2,
                        "z": 0.3,
                    }
                ]
            ),
            "SELECT code, cluster_id FROM cluster_results",
            [("600519", 1)],
        ),
    ],
)
def test_store_save_methods_persist_pandas_frames(tmp_path, method_name, frame, query, expected):
    from engine.data.store import DuckDBStore

    store = DuckDBStore(db_path=tmp_path / "store.duckdb")

    getattr(store, method_name)(frame)

    rows = store._conn.execute(query).fetchall()
    assert rows == expected


def test_get_snapshot_as_of_falls_back_to_stock_daily_when_snapshot_daily_missing(tmp_path):
    from engine.data.store import DuckDBStore

    store = DuckDBStore(db_path=tmp_path / "store.duckdb")
    store.save_daily(
        pd.DataFrame(
            [
                {
                    "code": "000001",
                    "date": "2026-03-20",
                    "open": 10.0,
                    "high": 10.2,
                    "low": 9.9,
                    "close": 10.1,
                    "volume": 100000,
                    "amount": 1.01e6,
                    "pct_chg": 1.2,
                    "turnover_rate": 0.5,
                },
                {
                    "code": "600519",
                    "date": "2026-03-20",
                    "open": 1800.0,
                    "high": 1810.0,
                    "low": 1790.0,
                    "close": 1805.0,
                    "volume": 12345,
                    "amount": 2.2e7,
                    "pct_chg": 0.8,
                    "turnover_rate": 0.3,
                },
            ]
        )
    )

    snapshot = store.get_snapshot_as_of("2026-03-20")

    assert list(snapshot["code"]) == ["000001", "600519"]
    assert list(snapshot["name"]) == ["000001", "600519"]
    assert list(snapshot["price"]) == [10.1, 1805.0]
    assert list(snapshot["pct_chg"]) == [1.2, 0.8]
