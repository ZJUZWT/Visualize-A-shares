from pathlib import Path

from config import settings


def test_local_cors_defaults_allow_127_loopback() -> None:
    assert "http://127.0.0.1:3000" in settings.server.cors_origins
    assert "http://127.0.0.1:5173" in settings.server.cors_origins


def test_docker_compose_backend_cors_allows_127_loopback() -> None:
    compose_text = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000" in compose_text
