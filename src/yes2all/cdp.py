"""Minimal Chrome DevTools Protocol client over WebSocket."""
from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from typing import Any

import httpx
import websockets


@dataclass
class Target:
    id: str
    type: str
    title: str
    url: str
    ws_url: str

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Target":
        return cls(
            id=d.get("id", ""),
            type=d.get("type", ""),
            title=d.get("title", ""),
            url=d.get("url", ""),
            ws_url=d.get("webSocketDebuggerUrl", ""),
        )


async def list_targets(port: int = 9222, host: str = "localhost") -> list[Target]:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"http://{host}:{port}/json")
        r.raise_for_status()
        return [Target.from_json(t) for t in r.json()]


async def list_pages(port: int = 9222, host: str = "localhost") -> list[Target]:
    return [t for t in await list_targets(port, host) if t.type == "page"]


class CDPSession:
    """Tiny CDP client speaking the per-target WebSocket directly."""

    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._ids = itertools.count(1)

    async def __aenter__(self) -> "CDPSession":
        # Cursor/Electron sends large DOM payloads; raise default limit.
        self._ws = await websockets.connect(self.ws_url, max_size=64 * 1024 * 1024)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert self._ws is not None, "session not opened"
        msg_id = next(self._ids)
        payload = {"id": msg_id, "method": method, "params": params or {}}
        await self._ws.send(json.dumps(payload))
        # Drain until we get the matching response. Ignore unrelated events.
        while True:
            raw = await self._ws.recv()
            data = json.loads(raw)
            if data.get("id") == msg_id:
                if "error" in data:
                    raise RuntimeError(f"CDP error for {method}: {data['error']}")
                return data.get("result", {})

    async def evaluate(self, expression: str, return_by_value: bool = True) -> Any:
        result = await self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": return_by_value,
                "awaitPromise": True,
            },
        )
        ro = result.get("result", {})
        if ro.get("subtype") == "error":
            raise RuntimeError(f"JS error: {ro.get('description')}")
        return ro.get("value")
