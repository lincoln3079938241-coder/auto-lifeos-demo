from __future__ import annotations

from schemas.meal_plan import MealPlan
from agent.nodes.guardrails import validate_plan
from agent.nodes.shared import update_with_audit


def validate_generated_plan(state: dict) -> dict:
    if not state.get("proposed_plan"):
        return update_with_audit(state, "validate_plan", "无方案可校验", validation_errors=state.get("validation_errors", ["无方案"]))
    try:
        plan = MealPlan.model_validate(state["proposed_plan"])
        errors = validate_plan(plan, state["user_profile"], state["inventory_snapshot"])
    except Exception as exc:
        errors = [f"Pydantic/规则校验失败：{exc}"]
    summary = "校验通过" if not errors else f"校验发现 {len(errors)} 个问题"
    return update_with_audit(state, "validate_plan", summary, validation_errors=errors)


def plan_revision(state: dict) -> dict:
    return update_with_audit(state, "plan_revision", "根据校验错误重新生成", retry_count=state.get("retry_count", 0) + 1,
                             proposed_plan={})

