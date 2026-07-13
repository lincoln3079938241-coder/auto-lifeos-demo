from __future__ import annotations

from agent.nodes.shared import update_with_audit


def inventory_query_response(state: dict) -> dict:
    count = len(state.get("inventory_snapshot", []))
    return update_with_audit(state, "inventory_query_response", f"已读取 {count} 条库存", final_message="当前库存已读取，请在库存页面查看有效、临期和过期项目。")


def fallback_handler(state: dict) -> dict:
    intent = state.get("intent", "unknown")
    if intent == "inventory_query":
        message = "当前库存已读取，请在库存页面查看有效、临期和过期项目。"
    elif state.get("validation_errors"):
        message = "无法生成可执行方案：" + "；".join(state["validation_errors"])
    elif state.get("error"):
        message = "流程未执行：" + state["error"]
    elif state.get("first_confirmation") is False:
        message = "已拒绝本次方案，库存没有变化。"
    elif state.get("second_confirmation") is False:
        message = "已取消库存扣减，库存没有变化。"
    else:
        message = "未能识别需求。可尝试：今晚想吃高蛋白、低脂、30 分钟以内的食物。"
    return update_with_audit(state, "fallback_handler", message, final_message=message)


def final_response(state: dict) -> dict:
    if state.get("transaction_id"):
        message = f"已完成两阶段确认和库存扣减，事务编号：{state['transaction_id']}。"
    elif state.get("proposed_plan") and state.get("first_confirmation") is None:
        message = "方案已生成，请先确认；未确认前不会扣减库存。"
    elif state.get("proposed_plan") and state.get("second_confirmation") is None:
        message = "请核对实际食用量并进行第二次确认；未确认前不会扣减库存。"
    else:
        message = state.get("final_message") or "流程结束。"
    return update_with_audit(state, "final_response", message, final_message=message)
