from __future__ import annotations

from agent.graph import run_agent
from agent.state import initial_state
from database.repositories import latest_executable_transaction, list_inventory
from database.seed import DEMO_USER_ID
from database.session import get_session
from database.transactions import undo_transaction
from session_store import SessionWorkspace


QUERY = "今晚想吃高蛋白、低脂、30分钟以内可以完成的食物。"


def quantities(workspace: SessionWorkspace) -> dict[str, float]:
    workspace.activate()
    with get_session() as session:
        return {row["canonical_item_id"]: row["quantity"] for row in list_inventory(session, DEMO_USER_ID)}


def execute_meal(workspace: SessionWorkspace) -> dict:
    workspace.activate()
    state = run_agent(initial_state(workspace.session_id, DEMO_USER_ID, QUERY))
    state["first_confirmation"] = True
    state = run_agent(state)
    state["second_confirmation"] = True
    return run_agent(state)


def test_two_sessions_use_different_databases() -> None:
    first, second = SessionWorkspace(), SessionWorkspace()
    try:
        assert first.session_id != second.session_id
        assert first.database_path != second.database_path
    finally:
        first.close()
        second.close()


def test_session_a_deduction_does_not_affect_session_b() -> None:
    first, second = SessionWorkspace(), SessionWorkspace()
    try:
        baseline_b = quantities(second)
        state = execute_meal(first)
        assert state["transaction_id"]
        assert quantities(first)["chicken_breast"] == 1320
        assert quantities(second) == baseline_b
    finally:
        first.close()
        second.close()


def test_session_a_undo_does_not_affect_session_b() -> None:
    first, second = SessionWorkspace(), SessionWorkspace()
    try:
        baseline_a = quantities(first)
        baseline_b = quantities(second)
        execute_meal(first)
        first.activate()
        with get_session() as session:
            transaction = latest_executable_transaction(session, DEMO_USER_ID)
            assert transaction is not None
            undo_transaction(session, transaction.id, first.session_id)
        assert quantities(first) == baseline_a
        assert quantities(second) == baseline_b
    finally:
        first.close()
        second.close()


def test_new_session_starts_from_baseline_inventory() -> None:
    changed, fresh = SessionWorkspace(), SessionWorkspace()
    try:
        execute_meal(changed)
        assert quantities(changed)["chicken_breast"] < 1500
        assert quantities(fresh)["chicken_breast"] == 1500
        assert quantities(fresh)["tomato"] == 400
        assert quantities(fresh)["rice"] == 2000
    finally:
        changed.close()
        fresh.close()
