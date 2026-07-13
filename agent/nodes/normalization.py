from __future__ import annotations

import re
from database.models import FoodAlias
from database.session import get_session
from services.alias_mapper import map_alias
from agent.nodes.shared import update_with_audit


def normalize_entities(state: dict) -> dict:
    query = state["raw_query"]
    minutes_match = re.search(r"(\d+)\s*分钟", query)
    max_minutes = int(minutes_match.group(1)) if minutes_match else 30
    found = []
    with get_session() as session:
        aliases = [row.alias for row in session.query(FoodAlias).all()]
        for alias in aliases:
            if alias.lower() in query.lower():
                mapped = map_alias(session, alias)
                if mapped["canonical_item_id"] and mapped not in found:
                    found.append(mapped)
    requirements = {"query": query, "max_minutes": max_minutes,
                    "high_protein": any(x in query.lower() for x in ["高蛋白", "蛋白"]),
                    "low_fat": "低脂" in query, "vegetarian": any(x in query for x in ["素食", "素餐"]),
                    "entities": found}
    return update_with_audit(state, "normalize_entities", f"规范化 {len(found)} 个食材实体；烹饪上限 {max_minutes} 分钟",
                             normalized_requirements=requirements)

