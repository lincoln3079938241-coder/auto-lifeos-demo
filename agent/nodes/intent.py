from __future__ import annotations

from agent.nodes.shared import update_with_audit


def intent_router(state: dict) -> dict:
    query = state["raw_query"].lower()
    if any(word in query for word in ["库存", "还有多少", "余量"]): intent = "inventory_query"
    elif any(word in query for word in ["添加库存", "补货", "入库"]): intent = "inventory_add"
    elif any(word in query for word in ["记录饮食", "我吃了", "记录吃"]): intent = "food_record"
    elif any(word in query for word in ["更新档案", "修改偏好", "过敏", "忌口"]): intent = "profile_update"
    elif any(word in query for word in ["吃", "餐", "蛋白", "早餐", "晚餐", "推荐", "饭"]): intent = "meal_recommendation"
    else: intent = "unknown"
    return update_with_audit(state, "intent_router", f"识别意图：{intent}", intent=intent)

