from __future__ import annotations

import json


class FakeTransport:
    """Queue-based fake for llm transport. Register responses per url suffix."""

    def __init__(self):
        self.queues: dict[str, list[dict]] = {}
        self.calls: list[tuple[str, dict | None]] = []

    def add(self, suffix: str, response: dict):
        self.queues.setdefault(suffix, []).append(response)

    def add_chat_json(self, obj):
        self.add("/api/chat", {"message": {"content": json.dumps(obj)}})

    def __call__(self, url: str, payload: dict | None) -> dict:
        self.calls.append((url, payload))
        for suffix, queue in self.queues.items():
            if url.endswith(suffix):
                if not queue:
                    raise AssertionError(f"no queued response left for {suffix}")
                return queue.pop(0)
        raise AssertionError(f"unexpected url {url}")
