from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

DEFAULT_HOST = "http://localhost:11434"
PREFERRED_MODELS = ("qwen3:14b", "granite3.3:8b")
EMBED_MODEL = "granite-embedding:30m"
_THINK_RE = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL)


class LlmError(Exception):
    pass


def _default_transport(url: str, payload: dict | None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise LlmError(f"cannot reach ollama at {url}; is `ollama serve` running? ({e})")


class OllamaClient:
    def __init__(self, host: str | None = None, transport=None):
        self.host = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_HOST).rstrip("/")
        self.transport = transport or _default_transport

    def list_models(self) -> list[str]:
        r = self.transport(f"{self.host}/api/tags", None)
        return [m["name"] for m in r.get("models", [])]

    def pick_model(self) -> str:
        env = os.environ.get("THROUGHLINE_MODEL")
        if env:
            return env
        names = self.list_models()
        for want in PREFERRED_MODELS:
            if any(n == want or n.startswith(want) for n in names):
                return want
        raise LlmError(
            f"no reasoning model found; run `ollama pull {PREFERRED_MODELS[0]}` "
            f"or set THROUGHLINE_MODEL (installed: {names})"
        )

    def generate(self, prompt: str, *, system: str = "", schema: dict | None = None,
                 validate=None, model: str | None = None, retries: int = 2) -> dict:
        model = model or self.pick_model()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        last_errors: list[str] = []
        for _ in range(retries + 1):
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.2},
            }
            if schema is not None:
                payload["format"] = schema
            r = self.transport(f"{self.host}/api/chat", payload)
            content = _THINK_RE.sub("", r["message"]["content"]).strip()
            try:
                obj = json.loads(content)
            except json.JSONDecodeError as e:
                last_errors = [f"reply was not valid JSON: {e}"]
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": self._retry_prompt(last_errors)})
                continue
            errors = validate(obj) if validate else []
            if not errors:
                return obj
            last_errors = errors
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": self._retry_prompt(errors)})
        raise LlmError(f"model output failed validation after retries: {last_errors}")

    @staticmethod
    def _retry_prompt(errors: list[str]) -> str:
        listed = "; ".join(errors)
        return (
            f"Your previous reply had these problems: {listed}. "
            "Reply again with corrected JSON only, no commentary."
        )

    def embed(self, texts: list[str], model: str = EMBED_MODEL) -> list[list[float]]:
        r = self.transport(f"{self.host}/api/embed", {"model": model, "input": texts})
        return r["embeddings"]
