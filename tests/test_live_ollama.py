import urllib.request

import pytest

import llm


def _server_up() -> bool:
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _server_up(), reason="ollama server not running")


def test_live_pick_model_and_tiny_generate():
    client = llm.OllamaClient()
    try:
        model = client.pick_model()
    except llm.LlmError:
        pytest.skip("no preferred reasoning model installed")
    out = client.generate(
        'Reply with JSON {"ok": true}',
        schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        model=model, retries=1,
    )
    assert out["ok"] is True


def test_live_embeddings():
    client = llm.OllamaClient()
    if llm.EMBED_MODEL.split(":")[0] not in " ".join(client.list_models()):
        pytest.skip("embedding model not installed")
    vecs = client.embed(["hello", "world"])
    assert len(vecs) == 2 and len(vecs[0]) > 10
