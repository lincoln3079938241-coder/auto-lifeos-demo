from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    session_id: str
    user_id: str
    raw_query: str
    intent: str
    user_profile: dict[str, Any]
    retrieved_context: list[dict[str, Any]]
    inventory_snapshot: list[dict[str, Any]]
    normalized_requirements: dict[str, Any]
    proposed_plan: dict[str, Any]
    validation_errors: list[str]
    warnings: list[str]
    first_confirmation: bool | None
    actual_consumption: list[dict[str, Any]]
    second_confirmation: bool | None
    transaction_id: str | None
    audit_events: list[dict[str, Any]]
    retry_count: int
    current_node: str
    final_message: str
    error: str | None
    provider_note: str


def initial_state(session_id: str, user_id: str, raw_query: str, **updates: Any) -> AgentState:
    base: AgentState = {"session_id": session_id, "user_id": user_id, "raw_query": raw_query,
                        "intent": "unknown", "retrieved_context": [], "inventory_snapshot": [],
                        "normalized_requirements": {}, "validation_errors": [], "warnings": [],
                        "first_confirmation": None, "actual_consumption": [], "second_confirmation": None,
                        "transaction_id": None, "audit_events": [], "retry_count": 0,
                        "current_node": "start", "final_message": "", "error": None}
    base.update(updates)
    return base

