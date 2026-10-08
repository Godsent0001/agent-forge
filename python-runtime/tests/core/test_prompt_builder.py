from app.contracts.graph import AgentSpec
from app.core.prompt_builder import build_system_prompt


def test_build_system_prompt_stable_and_volatile_order():
    spec = AgentSpec(
        id="a1",
        name="Research Assistant",
        description="Gathers facts on requested topics.",
        provider="fake",
        model="fake-model",
        system_prompt="Be concise and helpful.",
        tool_guidance="Use web_search before answering factual queries.",
        memory_enabled=True,
        lessons_enabled=True,
    )

    prompt = build_system_prompt(
        spec=spec,
        memory_block="- [fact] User prefers bullet points",
        reminders_block="- Check server status",
        recent_runs_block="- 2026-10-06 error in search",
        plan_block="1. [done] Search news\n2. [doing] Summarize results",
        lessons_block="- Avoid single word queries in search",
        history_summary_block="User previously discussed AI architectures.",
    )

    assert "<role>" in prompt
    assert "Research Assistant" in prompt
    assert "<instructions>" in prompt
    assert "<tool_guidance>" in prompt
    assert "<lessons>" in prompt
    assert "<plan>" in prompt
    assert "<reminders>" in prompt
    assert "<memory>" in prompt
    assert "<recent_runs trust=\"untrusted\">" in prompt
    assert "<conversation_summary>" in prompt

    # Verify stable content comes before volatile content
    lessons_idx = prompt.index("<lessons>")
    plan_idx = prompt.index("<plan>")
    memory_idx = prompt.index("<memory>")

    assert lessons_idx < plan_idx
    assert plan_idx < memory_idx
