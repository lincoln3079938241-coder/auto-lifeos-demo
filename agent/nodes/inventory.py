from __future__ import annotations

from database.repositories import list_inventory
from database.session import get_session
from agent.nodes.shared import update_with_audit


def load_inventory(state: dict) -> dict:
    with get_session() as session:
        inventory = list_inventory(session, state["user_id"])
    return update_with_audit(state, "load_inventory", f"读取 {len(inventory)} 条结构化库存", inventory_snapshot=inventory)

