"""Shared online HTTP bridge for agent MCP tools."""
from __future__ import annotations

import os
from typing import Any

import httpx

_DEFAULT_AGENT_API_BASE = "http://localhost:8000"


def _api_base() -> str:
    return os.getenv("AGENT_API_BASE", _DEFAULT_AGENT_API_BASE).rstrip("/")


def _build_url(path: str) -> str:
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{_api_base()}{path}"


def _extract_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        for key in ("detail", "message", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value

    text = response.text.strip()
    return text or f"HTTP {response.status_code}"


async def request_agent_json(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                _build_url(path),
                params=params,
                json=payload,
                timeout=timeout,
            )
    except httpx.RequestError as exc:
        raise ValueError(f"Agent service unavailable: {exc}") from exc

    if response.status_code >= 400:
        raise ValueError(_extract_error_message(response))

    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError(f"Agent service returned invalid JSON for {path}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Agent service returned unexpected payload for {path}")
    return data


async def get_agent_json(
    path: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    return await request_agent_json("GET", path, params=params, timeout=timeout)


async def post_agent_json(
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    return await request_agent_json("POST", path, payload=payload, timeout=timeout)
