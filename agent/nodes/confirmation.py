from __future__ import annotations

from agent.nodes.shared import update_with_audit


def wait_first_confirmation(state: dict) -> dict:
    answer = state.get("first_confirmation")
    detail = "等待用户确认方案" if answer is None else ("用户接受方案" if answer else "用户拒绝方案")
    return update_with_audit(state, "wait_first_confirmation", detail)


def collect_actual_consumption(state: dict) -> dict:
    actual = state.get("actual_consumption") or [
        {"canonical_item_id": item["canonical_item_id"], "amount": item["amount"], "unit": item["unit"]}
        for item in state["proposed_plan"]["ingredients"]]
    return update_with_audit(state, "collect_actual_consumption", f"收集到 {len(actual)} 项实际食用量", actual_consumption=actual)


def wait_second_confirmation(state: dict) -> dict:
    answer = state.get("second_confirmation")
    detail = "等待用户确认库存扣减" if answer is None else ("用户确认扣减" if answer else "用户拒绝扣减")
    return update_with_audit(state, "wait_second_confirmation", detail)

