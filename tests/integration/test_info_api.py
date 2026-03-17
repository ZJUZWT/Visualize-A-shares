# tests/test_info_api.py
"""InfoEngine REST API 测试"""
import pytest


class TestInfoRoutes:
    def test_info_router_exists(self):
        from engine.info.routes import router
        assert router.prefix == "/api/v1/info"

    def test_info_router_registered_in_app(self):
        from main import app
        paths = [r.path for r in app.routes]
        assert any("/api/v1/info" in p for p in paths)

    def test_health_endpoint_exists(self):
        from engine.info.routes import router
        route_paths = [r.path for r in router.routes]
        assert any("/health" in p for p in route_paths)
