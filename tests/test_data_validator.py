"""DataValidator 单元测试 — 覆盖所有校验规则"""

import json
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from engine.expert.data_validator import DataValidator, ValidationResult


class TestStockSnapshot:
    """query_stock 校验"""

    def test_valid_stock(self):
        """正常股票数据应该通过校验"""
        data = json.dumps({
            "code": "000001", "name": "平安银行", "price": 12.5,
            "pct_chg": 2.1, "volume": 50000000, "amount": 625000000,
            "high": 12.8, "low": 12.2, "open": 12.3,
            "pe_ttm": 6.5, "pb": 0.8, "total_mv": 2400,
        })
        result = DataValidator.validate("query_stock", data)
        parsed = json.loads(result)
        assert "_validation" not in parsed  # 无问题不注入

    def test_price_zero(self):
        """价格为0应该报错"""
        data = json.dumps({
            "code": "000001", "name": "平安银行", "price": 0,
            "pct_chg": 0, "volume": 0,
        })
        result = DataValidator.validate("query_stock", data)
        parsed = json.loads(result)
        assert "_validation" in parsed
        assert parsed["_validation"]["status"] == "error"
        assert any("价格异常" in i["msg"] for i in parsed["_validation"]["issues"])

    def test_extreme_pct_chg(self):
        """涨跌幅超限应该警告"""
        data = json.dumps({
            "code": "000001", "name": "平安银行", "price": 15.0,
            "pct_chg": 35.0, "volume": 100000,
            "high": 15.0, "low": 14.5, "open": 14.6,
        })
        result = DataValidator.validate("query_stock", data)
        parsed = json.loads(result)
        assert "_validation" in parsed
        assert any("涨跌幅异常" in i["msg"] for i in parsed["_validation"]["issues"])

    def test_new_stock_exempt(self):
        """新股 (N开头) 涨跌幅超限不报警"""
        data = json.dumps({
            "code": "301500", "name": "N新股", "price": 80.0,
            "pct_chg": 120.0, "volume": 100000,
            "high": 80.0, "low": 60.0, "open": 65.0,
        })
        result = DataValidator.validate("query_stock", data)
        parsed = json.loads(result)
        # 不应该有涨跌幅异常的警告
        if "_validation" in parsed:
            assert not any("涨跌幅异常" in i["msg"] for i in parsed["_validation"]["issues"])

    def test_ohlc_violation(self):
        """high < low 应该警告"""
        data = json.dumps({
            "code": "000001", "name": "平安银行", "price": 12.5,
            "pct_chg": 1.0, "volume": 50000000,
            "high": 12.0, "low": 13.0, "open": 12.5,  # high < low!
        })
        result = DataValidator.validate("query_stock", data)
        parsed = json.loads(result)
        assert "_validation" in parsed
        assert any("最高价" in i["msg"] and "最低价" in i["msg"] for i in parsed["_validation"]["issues"])

    def test_zero_volume_with_pct_change(self):
        """成交量为0但有涨跌幅应该警告"""
        data = json.dumps({
            "code": "000001", "name": "平安银行", "price": 12.5,
            "pct_chg": 5.0, "volume": 0,
            "high": 12.5, "low": 12.0, "open": 12.0,
        })
        result = DataValidator.validate("query_stock", data)
        parsed = json.loads(result)
        assert "_validation" in parsed
        assert any("成交量为0" in i["msg"] for i in parsed["_validation"]["issues"])

    def test_negative_pe(self):
        """负PE应该有info级提示"""
        data = json.dumps({
            "code": "000001", "name": "平安银行", "price": 12.5,
            "pct_chg": 1.0, "volume": 50000000,
            "pe_ttm": -15.0,
            "high": 12.8, "low": 12.2, "open": 12.3,
        })
        result = DataValidator.validate("query_stock", data)
        parsed = json.loads(result)
        assert "_validation" in parsed
        assert any("PE为负" in i["msg"] for i in parsed["_validation"]["issues"])


class TestKlineRecords:
    """query_history / query_hourly 校验"""

    def test_valid_kline(self):
        """正常K线数据"""
        data = json.dumps({
            "code": "000001",
            "records": [
                {"date": "2026-03-17", "open": 12.0, "high": 12.5, "low": 11.8, "close": 12.3, "volume": 50000, "pct_chg": 1.5},
                {"date": "2026-03-18", "open": 12.3, "high": 12.8, "low": 12.1, "close": 12.6, "volume": 60000, "pct_chg": 2.4},
            ],
            "total_days": 2,
        })
        result = DataValidator.validate("query_history", data)
        parsed = json.loads(result)
        assert "_validation" not in parsed

    def test_ohlc_violation_in_kline(self):
        """K线中 high < low"""
        data = json.dumps({
            "code": "000001",
            "records": [
                {"date": "2026-03-17", "open": 12.0, "high": 11.5, "low": 12.5, "close": 12.0, "volume": 50000, "pct_chg": 0},
            ],
            "total_days": 1,
        })
        result = DataValidator.validate("query_history", data)
        parsed = json.loads(result)
        assert "_validation" in parsed
        assert any("OHLC" in i["msg"] for i in parsed["_validation"]["issues"])

    def test_duplicate_dates(self):
        """重复日期检测"""
        data = json.dumps({
            "code": "000001",
            "records": [
                {"date": "2026-03-17", "open": 12.0, "high": 12.5, "low": 11.8, "close": 12.3, "volume": 50000, "pct_chg": 1.0},
                {"date": "2026-03-17", "open": 12.3, "high": 12.8, "low": 12.1, "close": 12.6, "volume": 60000, "pct_chg": 2.0},
            ],
            "total_days": 2,
        })
        result = DataValidator.validate("query_history", data)
        parsed = json.loads(result)
        assert "_validation" in parsed
        assert any("重复日期" in i["msg"] for i in parsed["_validation"]["issues"])

    def test_close_price_zero(self):
        """收盘价为0应该报错"""
        data = json.dumps({
            "code": "000001",
            "records": [
                {"date": "2026-03-17", "open": 12.0, "high": 12.5, "low": 11.8, "close": 0, "volume": 50000, "pct_chg": -100},
            ],
            "total_days": 1,
        })
        result = DataValidator.validate("query_history", data)
        parsed = json.loads(result)
        assert "_validation" in parsed
        assert parsed["_validation"]["status"] == "error"


class TestMarketOverview:
    """query_market_overview 校验"""

    def test_valid_overview(self):
        """正常市场概览"""
        data = json.dumps({
            "total_stocks": 5200, "up": 2600, "down": 2300, "flat": 300,
            "updated_at": "",
        })
        result = DataValidator.validate("query_market_overview", data)
        parsed = json.loads(result)
        assert "_validation" not in parsed

    def test_low_total_stocks(self):
        """股票总数过低应该警告"""
        data = json.dumps({
            "total_stocks": 500, "up": 200, "down": 200, "flat": 100,
        })
        result = DataValidator.validate("query_market_overview", data)
        parsed = json.loads(result)
        assert "_validation" in parsed
        assert any("总数异常" in i["msg"] for i in parsed["_validation"]["issues"])

    def test_inconsistent_total(self):
        """涨+跌+平 ≠ 总数"""
        data = json.dumps({
            "total_stocks": 5200, "up": 2600, "down": 2300, "flat": 100,
        })
        result = DataValidator.validate("query_market_overview", data)
        parsed = json.loads(result)
        assert "_validation" in parsed
        assert any("不一致" in i["msg"] for i in parsed["_validation"]["issues"])


class TestTechnicalIndicators:
    """get_technical_indicators 校验"""

    def test_invalid_rsi(self):
        """RSI 超出 [0,100] 范围"""
        data = json.dumps({
            "code": "000001", "data_days": 60,
            "indicators": {"rsi_14": 150, "macd": 0.5},
        })
        result = DataValidator.validate("get_technical_indicators", data)
        parsed = json.loads(result)
        assert "_validation" in parsed
        assert parsed["_validation"]["status"] == "error"

    def test_low_data_days(self):
        """数据天数不足"""
        data = json.dumps({
            "code": "000001", "data_days": 15,
            "indicators": {"rsi_14": 55, "macd": 0.5},
        })
        result = DataValidator.validate("get_technical_indicators", data)
        parsed = json.loads(result)
        assert "_validation" in parsed
        assert any("天" in i["msg"] for i in parsed["_validation"]["issues"])


class TestFactorScores:
    """get_factor_scores 校验"""

    def test_many_null_factors(self):
        """超过50%因子缺失"""
        data = json.dumps({
            "code": "000001",
            "factors": {
                "pe": {"value": None, "weight": 0.5},
                "pb": {"value": None, "weight": 0.3},
                "roe": {"value": None, "weight": 0.2},
                "momentum": {"value": 1.5, "weight": 0.1},
            },
        })
        result = DataValidator.validate("get_factor_scores", data)
        parsed = json.loads(result)
        assert "_validation" in parsed
        assert any("缺失" in i["msg"] for i in parsed["_validation"]["issues"])


class TestEdgeCases:
    """边界情况"""

    def test_non_json_passthrough(self):
        """非JSON字符串应该原样返回"""
        result = DataValidator.validate("query_stock", "这不是JSON")
        assert result == "这不是JSON"

    def test_error_response_passthrough(self):
        """已有error的响应不应该再校验"""
        data = json.dumps({"error": "未找到 000001"})
        result = DataValidator.validate("query_stock", data)
        parsed = json.loads(result)
        assert "_validation" not in parsed

    def test_empty_response_passthrough(self):
        """empty响应不应该再校验"""
        data = json.dumps({"empty": True, "note": "无数据"})
        result = DataValidator.validate("query_stock", data)
        parsed = json.loads(result)
        assert "_validation" not in parsed

    def test_unknown_skill_passthrough(self):
        """未知skill应该跳过校验"""
        data = json.dumps({"code": "000001", "price": -100})
        result = DataValidator.validate("unknown_skill", data)
        parsed = json.loads(result)
        assert "_validation" not in parsed
