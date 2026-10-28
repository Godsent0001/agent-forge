from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.contracts.graph import AgentSpec, LLMParams
from app.core.llm.types import LLMTurn, Usage
from app.core.runner import RunnerCore


class _MemoryStore:
    def __init__(self):
        self.added = []

    async def related(self, agent_id, query, limit=20):
        return []

    async def add(self, agent_id, candidates):
        self.added.extend(candidates)
        return [SimpleNamespace(id=f"memory-{index}") for index, _ in enumerate(candidates, start=1)]


class _Budget:
    def __init__(self):
        self.calls = []

    def check_limits(self):
        return None

    def record_llm_call(self, **kwargs):
        self.calls.append(kwargs)


@pytest.mark.asyncio
async def test_production_memory_extraction_uses_configured_llm_adapter(monkeypatch):
    memory = _MemoryStore()
    budget = _Budget()
    calls = {}
    spec = AgentSpec(
        id="system-engineer",
        name="System Engineer",
        provider="venice",
        model="deepseek-v4-1-flash",
        memory_enabled=True,
        params=LLMParams(max_tokens=4096),
    )
    request = SimpleNamespace(
        task="Remember that I prefer concise answers.",
        history=[],
        execution_id="run-memory-1",
    )

    async def fake_adapter_complete(*, messages, params, model):
        calls["messages"] = messages
        calls["max_tokens"] = params.max_tokens
        calls["model"] = model
        return LLMTurn(
            text=json.dumps({
                "memories": [{
                    "text": "User prefers concise answers",
                    "kind": "preference",
                    "evidence": "I prefer concise answers",
                }]
            }),
            usage=Usage(input_tokens=20, output_tokens=15),
            cost_usd=0.001,
        )

    monkeypatch.setattr("app.core.runner.adapter_complete", fake_adapter_complete)
    monkeypatch.setattr("app.core.runner.litellm_model", lambda provider, model: f"{provider}/{model}")

    async def emit(event):
        return None

    await RunnerCore()._extract_memories(
        spec,
        request,
        "I will keep replies concise.",
        memory,
        emit,
        None,
        budget,
    )

    assert calls["model"] == "venice/deepseek-v4-1-flash"
    assert calls["max_tokens"] == 512
    assert len(memory.added) == 1
    assert memory.added[0].text == "User prefers concise answers"
    assert budget.calls[0]["input_tokens"] == 20
