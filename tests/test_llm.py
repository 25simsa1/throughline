import pytest

import llm
from tests.fakes import FakeTransport


def _client(ft):
    return llm.OllamaClient(host="http://fake:11434", transport=ft)


def test_pick_model_prefers_qwen_then_granite(monkeypatch):
    monkeypatch.delenv("THROUGHLINE_MODEL", raising=False)
    ft = FakeTransport()
    ft.add("/api/tags", {"models": [{"name": "granite3.3:8b"}, {"name": "qwen3:14b"}]})
    assert _client(ft).pick_model() == "qwen3:14b"
    ft2 = FakeTransport()
    ft2.add("/api/tags", {"models": [{"name": "granite3.3:8b"}]})
    assert _client(ft2).pick_model() == "granite3.3:8b"


def test_pick_model_returns_matched_variant_tag(monkeypatch):
    monkeypatch.delenv("THROUGHLINE_MODEL", raising=False)
    ft = FakeTransport()
    ft.add("/api/tags", {"models": [{"name": "qwen3:14b-instruct-q4"}]})
    assert _client(ft).pick_model() == "qwen3:14b-instruct-q4"


def test_pick_model_env_override(monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "mistral:7b")
    assert _client(FakeTransport()).pick_model() == "mistral:7b"


def test_pick_model_errors_when_nothing_usable(monkeypatch):
    monkeypatch.delenv("THROUGHLINE_MODEL", raising=False)
    ft = FakeTransport()
    ft.add("/api/tags", {"models": [{"name": "granite-embedding:30m"}]})
    with pytest.raises(llm.LlmError):
        _client(ft).pick_model()


def test_generate_parses_json_and_strips_think(monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ft = FakeTransport()
    ft.add("/api/chat", {"message": {"content": "<think>hmm</think>{\"a\": 1}"}})
    out = _client(ft).generate("p", schema={"type": "object"})
    assert out == {"a": 1}
    url, payload = ft.calls[-1]
    assert payload["format"] == {"type": "object"}
    assert payload["stream"] is False


def test_generate_retries_on_validation_errors(monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ft = FakeTransport()
    ft.add_chat_json({"n": 1})
    ft.add_chat_json({"n": 2})
    calls = []

    def validate(obj):
        calls.append(obj)
        return [] if obj["n"] == 2 else ["n must be 2"]

    out = _client(ft).generate("p", validate=validate, retries=2)
    assert out == {"n": 2}
    assert "n must be 2" in ft.calls[-1][1]["messages"][-1]["content"]


def test_generate_raises_after_retries_exhausted(monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "m")
    ft = FakeTransport()
    ft.add_chat_json({"n": 1})
    ft.add_chat_json({"n": 1})
    with pytest.raises(llm.LlmError):
        _client(ft).generate("p", validate=lambda o: ["bad"], retries=1)


def test_embed_returns_vectors(monkeypatch):
    ft = FakeTransport()
    ft.add("/api/embed", {"embeddings": [[0.1, 0.2], [0.3, 0.4]]})
    vecs = _client(ft).embed(["a", "b"])
    assert vecs == [[0.1, 0.2], [0.3, 0.4]]
    assert ft.calls[-1][1]["model"] == llm.EMBED_MODEL


def test_generate_disables_thinking_for_qwen3(monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "qwen3:14b")
    ft = FakeTransport()
    ft.add_chat_json({"a": 1})
    _client(ft).generate("p", schema={"type": "object"})
    assert ft.calls[-1][1]["think"] is False


def test_generate_leaves_thinking_alone_for_granite(monkeypatch):
    monkeypatch.setenv("THROUGHLINE_MODEL", "granite3.3:8b")
    ft = FakeTransport()
    ft.add_chat_json({"a": 1})
    _client(ft).generate("p", schema={"type": "object"})
    assert "think" not in ft.calls[-1][1]
