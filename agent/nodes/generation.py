from __future__ import annotations

from llm.base import get_provider
from agent.nodes.shared import update_with_audit


def generate_plan(state: dict) -> dict:
    if state.get("proposed_plan") and state.get("first_confirmation") is not None:
        return update_with_audit(state, "generate_plan", "保留已生成方案，等待后续确认")
    provider, note = get_provider()
    try:
        plan = provider.generate(state["normalized_requirements"], state.get("eligible_inventory", state["inventory_snapshot"]),
                                 state.get("retrieved_context", []), state["user_profile"])
        return update_with_audit(state, "generate_plan", f"{provider.name} 生成 Pydantic 结构化方案",
                                 proposed_plan=plan.model_dump(), provider_note=note, validation_errors=[])
    except Exception as exc:
        return update_with_audit(state, "generate_plan", "生成失败", error=str(exc), validation_errors=[str(exc)])

