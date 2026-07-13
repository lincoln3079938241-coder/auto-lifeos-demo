from __future__ import annotations

from database.repositories import save_diet_record, save_meal_plan
from database.session import get_session
from database.transactions import execute_deduction
from agent.nodes.shared import update_with_audit


def execute_inventory_transaction(state: dict) -> dict:
    if not (state.get("first_confirmation") and state.get("second_confirmation")):
        return update_with_audit(state, "execute_inventory_transaction", "确认不足，拒绝扣减", error="缺少两阶段确认")
    try:
        with get_session() as session:
            transaction_id = execute_deduction(session, state["user_id"], state["proposed_plan"]["plan_id"], state["actual_consumption"])
        return update_with_audit(state, "execute_inventory_transaction", "数据库事务已扣减库存", transaction_id=transaction_id)
    except Exception as exc:
        return update_with_audit(state, "execute_inventory_transaction", "库存事务回滚", error=str(exc))


def write_diet_record(state: dict) -> dict:
    if not state.get("transaction_id"):
        return update_with_audit(state, "write_diet_record", "未写入饮食记录：没有成功事务")
    nutrition = {key: state["proposed_plan"][key] for key in ["calories_kcal", "protein_g", "carbs_g", "fat_g"]}
    with get_session() as session:
        save_meal_plan(session, state["user_id"], state["raw_query"], state["proposed_plan"]["plan_id"],
                       __import__("json").dumps(state["proposed_plan"], ensure_ascii=False), status="executed")
        save_diet_record(session, state["user_id"], state["proposed_plan"]["plan_id"], state["actual_consumption"], nutrition)
    return update_with_audit(state, "write_diet_record", "饮食记录与方案已保存")


def write_audit_log(state: dict) -> dict:
    return update_with_audit(state, "write_audit_log", "关键节点审计日志已持久化", event_type="flow_complete")

