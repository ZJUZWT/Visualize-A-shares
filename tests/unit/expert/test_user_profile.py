"""UserProfileTracker 用户偏好追踪测试"""

import pytest

from engine.expert.user_profile import UserProfileTracker, extract_preferences


class TestExtractPreferences:
    def test_risk_aggressive(self):
        prefs = extract_preferences("我能承受50%的亏损，想做激进一点")
        assert prefs.get("risk") == "aggressive"

    def test_risk_conservative(self):
        prefs = extract_preferences("我比较保守，不能亏钱")
        assert prefs.get("risk") == "conservative"

    def test_sectors(self):
        prefs = extract_preferences("我最近很关注新能源和半导体")
        assert "新能源" in prefs.get("sectors", [])
        assert "半导体" in prefs.get("sectors", [])

    def test_style_short(self):
        prefs = extract_preferences("我喜欢做短线，快进快出")
        assert prefs.get("style") == "短线"

    def test_no_preferences(self):
        prefs = extract_preferences("你好")
        assert prefs == {}


class TestUserProfileTracker:
    @pytest.fixture
    def tracker(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        return UserProfileTracker(db_path)

    def test_update_and_get(self, tracker):
        tracker.update("global", {"risk": "aggressive", "sectors": ["新能源"]})
        profile = tracker.get("global")
        assert profile["risk"] == "aggressive"
        assert "新能源" in profile["sectors"]

    def test_merge_sectors(self, tracker):
        """sectors 应合并而非覆盖"""
        tracker.update("global", {"sectors": ["新能源"]})
        tracker.update("global", {"sectors": ["半导体"]})
        profile = tracker.get("global")
        assert "新能源" in profile["sectors"]
        assert "半导体" in profile["sectors"]

    def test_get_empty(self, tracker):
        profile = tracker.get("nonexistent")
        assert profile == {}

    def test_format_profile_prompt(self, tracker):
        tracker.update("global", {
            "risk": "conservative",
            "sectors": ["新能源", "半导体"],
            "style": "长线",
        })
        prompt = tracker.format_profile_prompt("global")
        assert "保守" in prompt or "conservative" in prompt
        assert "新能源" in prompt
