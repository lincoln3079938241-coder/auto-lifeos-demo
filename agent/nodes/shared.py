from __future__ import annotations

from typing import Any
from database.repositories import append_audit
from database.session import get_session


def update_with_audit(state: dict[str, Any], node: str, summary: str, **updates: Any) -> dict[str, Any]:
    events = list(state.get("audit_events", []))
    events.append({"node_name": node, "event_type": "node", "summary": summary,
                   "retry_count": state.get("retry_count", 0)})
    with get_session() as session:
        append_audit(session, state["session_id"], state["user_id"], "node", node, events[-1])
    return {"current_node": node, "audit_events": events, **updates}

