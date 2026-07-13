from __future__ import annotations

from agent.graph import run_agent
from agent.nodes.execution import execute_inventory_transaction
from agent.state import initial_state
from database.repositories import list_inventory
from database.seed import DEMO_USER_ID
from database.session import get_session
from session_store import SessionWorkspace


QUERY = "今晚想吃高蛋白、低脂、30分钟以内可以完成的食物。"


def chicken_quantity(workspace: SessionWorkspace) -> float:
    workspace.activate()
    with get_session() as session:
        rows = list_inventory(session, DEMO_USER_ID)
    return next(row["quantity"] for row in rows if row["canonical_item_id"] == "chicken_breast")


def proposed_state(workspace: SessionWorkspace) -> dict:
    workspace.activate()
    return run_agent(initial_state(workspace.session_id, DEMO_USER_ID, QUERY))


def test_no_deduction_before_first_confirmation() -> None:
    workspace = SessionWorkspace()
    try:
        state = proposed_state(workspace)
        result = execute_inventory_transaction(state)
        assert result["error"] == "缺少两阶段确认"
        assert chicken_quantity(workspace) == 1500
    finally:
        workspace.close()


def test_first_confirmation_alone_cannot_deduct() -> None:
    workspace = SessionWorkspace()
    try:
        state = proposed_state(workspace)
        state["first_confirmation"] = True
        state["second_confirmation"] = None
        result = execute_inventory_transaction(state)
        assert result["error"] == "缺少两阶段确认"
        assert chicken_quantity(workspace) == 1500
    finally:
        workspace.close()


def test_two_confirmations_allow_deduction() -> None:
    workspace = SessionWorkspace()
    try:
        state = proposed_state(workspace)
        state["first_confirmation"] = True
        state = run_agent(state)
        assert chicken_quantity(workspace) == 1500
        state["second_confirmation"] = True
        state = run_agent(state)
        assert state["transaction_id"]
        assert chicken_quantity(workspace) == 1320
    finally:
        workspace.close()

