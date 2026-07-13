from __future__ import annotations

import re
from database.models import FoodAlias
from database.session import get_session
from services.alias_mapper import map_alias
from agent.nodes.shared import update_with_audit


def normalize_entities(state: dict) -> dict:
    query = state["raw_query"]
    query_lower = query.lower()
    minutes_match = re.search(r"(\d+)\s*分钟", query)
    max_minutes = int(minutes_match.group(1)) if minutes_match else 30
    found = []
    with get_session() as session:
        aliases = [row.alias for row in session.query(FoodAlias).all()]
        for alias in aliases:
            if len(alias.strip()) < 2:
                continue
            if alias.lower() in query_lower:
                mapped = map_alias(session, alias)
                if mapped["canonical_item_id"] and mapped not in found:
                    found.append(mapped)
    meal_type = (
        "早餐" if any(x in query for x in ["早餐", "早饭", "早上"])
        else "午餐" if any(x in query for x in ["午餐", "中午"])
        else "晚餐" if any(x in query for x in ["晚餐", "今晚", "晚上"])
        else "轻食" if any(x in query for x in ["轻食", "沙拉"])
        else None
    )
    requirements = {"query": query, "max_minutes": max_minutes, "meal_type": meal_type,
                    "high_protein": any(x in query_lower for x in ["高蛋白", "蛋白"]),
                    "low_fat": "低脂" in query, "vegetarian": any(x in query for x in ["素食", "素餐"]),
                    "prefer_expiring": any(x in query for x in ["快过期", "即将过期", "优先使用快", "临期"]),
                    "home_style": any(x in query for x in ["家常", "快手家常"]),
                    "only_inventory": any(x in query for x in ["只使用", "仅使用"]),
                    "entities": found}
    return update_with_audit(state, "normalize_entities", f"规范化 {len(found)} 个食材实体；烹饪上限 {max_minutes} 分钟",
                             normalized_requirements=requirements)
