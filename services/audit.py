from __future__ import annotations

from typing import Any
from database.repositories import append_audit


def record_event(session, state: dict[str, Any], node_name: str, summary: str, event_type: str = "node") -> dict[str, Any]:
    event = {"node_name": node_name, "event_type": event_type, "summary": summary,
             "retry_count": state.get("retry_count", 0)}
    state.setdefault("audit_events", []).append(event)
    append_audit(session, state["session_id"], state["user_id"], event_type, node_name, event)
    return state

