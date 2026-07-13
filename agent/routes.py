from __future__ import annotations


def route_intent(state: dict) -> str:
    return "meal" if state.get("intent") == "meal_recommendation" else "inventory" if state.get("intent") == "inventory_query" else "fallback"


def route_validation(state: dict) -> str:
    if not state.get("validation_errors"):
        return "confirmed_plan"
    return "revise" if state.get("retry_count", 0) < 2 else "fallback"


def route_first_confirmation(state: dict) -> str:
    value = state.get("first_confirmation")
    return "accepted" if value is True else "rejected" if value is False else "wait"


def route_second_confirmation(state: dict) -> str:
    value = state.get("second_confirmation")
    return "accepted" if value is True else "rejected" if value is False else "wait"


def route_execution(state: dict) -> str:
    return "written" if state.get("transaction_id") else "fallback"

