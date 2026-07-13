from __future__ import annotations

from datetime import date, timedelta

import pytest

from agent.graph import run_agent
from agent.state import initial_state
from database.repositories import list_inventory, list_inventory_audit, list_inventory_transaction_lines
from database.seed import DEMO_USER_ID
from database.session import get_session
from services.inventory_editor import (
    InventoryInputError,
    add_inventory_item,
    restore_baseline_inventory,
    soft_delete_inventory_item,
    update_inventory_item,
)
from session_store import SessionWorkspace


QUERY = "今晚想吃高蛋白、低脂、30分钟以内可以完成的食物。"


def rows(workspace: SessionWorkspace, include_inactive: bool = False) -> list[dict]:
    workspace.activate()
    with get_session() as session:
        return list_inventory(session, DEMO_USER_ID, include_inactive=include_inactive)


def item(workspace: SessionWorkspace, food_id: str) -> dict:
    return next(row for row in rows(workspace) if row["canonical_item_id"] == food_id)


def add(workspace: SessionWorkspace, **overrides) -> dict:
    workspace.activate()
    values = {
        "name": "鲍鱼",
        "quantity": 500,
        "unit": "g",
        "expiration_date": None,
        "location": "冷藏",
        "request_id": None,
    }
    values.update(overrides)
    with get_session() as session:
        return add_inventory_item(session, workspace.session_id, DEMO_USER_ID, **values)


def update(workspace: SessionWorkspace, pantry_item_id: int, **overrides) -> None:
    workspace.activate()
    values = {
        "quantity": 300,
        "unit": "g",
        "expiration_date": None,
        "location": "冷藏",
        "request_id": None,
    }
    values.update(overrides)
    with get_session() as session:
        update_inventory_item(session, workspace.session_id, DEMO_USER_ID, pantry_item_id, **values)


def delete(workspace: SessionWorkspace, pantry_item_id: int) -> None:
    workspace.activate()
    with get_session() as session:
        soft_delete_inventory_item(session, workspace.session_id, DEMO_USER_ID, pantry_item_id)


def proposed(workspace: SessionWorkspace) -> dict:
    workspace.activate()
    return run_agent(initial_state(workspace.session_id, DEMO_USER_ID, QUERY))


def execute_meal(workspace: SessionWorkspace) -> dict:
    state = proposed(workspace)
    state["first_confirmation"] = True
    state = run_agent(state)
    state["second_confirmation"] = True
    return run_agent(state)


def test_new_session_receives_twenty_baseline_items() -> None:
    workspace = SessionWorkspace()
    try:
        assert len(rows(workspace)) == 20
        assert item(workspace, "chicken_breast")["quantity"] == 1500
    finally:
        workspace.close()


def test_add_standard_food_reactivates_soft_deleted_item() -> None:
    workspace = SessionWorkspace()
    try:
        chicken = item(workspace, "chicken_breast")
        delete(workspace, chicken["pantry_item_id"])
        result = add(workspace, name="鸡胸", quantity=600)
        assert result["canonical_item_id"] == "chicken_breast"
        assert result["action"] == "restore"
        assert item(workspace, "chicken_breast")["quantity"] == 600
    finally:
        workspace.close()


def test_add_unknown_custom_food_without_fabricated_nutrition() -> None:
    workspace = SessionWorkspace()
    try:
        result = add(workspace)
        tofu = item(workspace, result["canonical_item_id"])
        assert result["is_custom"] is True
        assert tofu["nutrition_available"] is False
        assert tofu["calories_per_100g"] is None
        assert tofu["protein_per_100g"] is None
    finally:
        workspace.close()


def test_duplicate_food_can_merge_quantity() -> None:
    workspace = SessionWorkspace()
    try:
        result = add(workspace, name="番茄", quantity=100, merge_existing=True)
        assert result["action"] == "merge"
        assert item(workspace, "tomato")["quantity"] == 500
    finally:
        workspace.close()


def test_alias_mapping_merges_into_canonical_food() -> None:
    workspace = SessionWorkspace()
    try:
        result = add(workspace, name="西红柿", quantity=50, merge_existing=True)
        assert result["canonical_name"] == "番茄"
        assert item(workspace, "tomato")["quantity"] == 450
        assert len([row for row in rows(workspace) if row["canonical_item_id"] == "tomato"]) == 1
    finally:
        workspace.close()


def test_update_quantity_and_unit() -> None:
    workspace = SessionWorkspace()
    try:
        chicken = item(workspace, "chicken_breast")
        update(workspace, chicken["pantry_item_id"], quantity=1.2, unit="kg")
        changed = item(workspace, "chicken_breast")
        assert changed["quantity"] == 1.2
        assert changed["unit"] == "kg"
    finally:
        workspace.close()


def test_update_expiration_date() -> None:
    workspace = SessionWorkspace()
    try:
        tomato = item(workspace, "tomato")
        target = date.today() + timedelta(days=10)
        update(workspace, tomato["pantry_item_id"], quantity=400, expiration_date=target.isoformat())
        assert item(workspace, "tomato")["expiration_date"] == target
    finally:
        workspace.close()


def test_delete_removes_food_from_recommendation_candidates() -> None:
    workspace = SessionWorkspace()
    try:
        delete(workspace, item(workspace, "chicken_breast")["pantry_item_id"])
        state = proposed(workspace)
        assert all(row["canonical_item_id"] != "chicken_breast" for row in state["inventory_snapshot"])
        assert all(
            ingredient["canonical_item_id"] != "chicken_breast"
            for ingredient in state["proposed_plan"]["ingredients"]
        )
    finally:
        workspace.close()


def test_delete_preserves_existing_meal_transaction_history() -> None:
    workspace = SessionWorkspace()
    try:
        state = execute_meal(workspace)
        assert state["transaction_id"]
        delete(workspace, item(workspace, "chicken_breast")["pantry_item_id"])
        workspace.activate()
        with get_session() as session:
            history = list_inventory_transaction_lines(session, DEMO_USER_ID)
        assert any(row["canonical_name"] == "鸡胸肉" for row in history)
    finally:
        workspace.close()


@pytest.mark.parametrize("quantity", [0, -1])
def test_zero_and_negative_quantity_are_rejected(quantity: float) -> None:
    workspace = SessionWorkspace()
    try:
        with pytest.raises(InventoryInputError, match="数量必须大于 0"):
            add(workspace, quantity=quantity)
    finally:
        workspace.close()


def test_non_numeric_and_excessive_quantity_are_rejected() -> None:
    workspace = SessionWorkspace()
    try:
        with pytest.raises(InventoryInputError, match="有效的数字"):
            add(workspace, quantity="很多")
        with pytest.raises(InventoryInputError, match="数量过大"):
            add(workspace, quantity=1_000_001)
    finally:
        workspace.close()


def test_blank_food_name_is_rejected() -> None:
    workspace = SessionWorkspace()
    try:
        with pytest.raises(InventoryInputError, match="请填写食材名称"):
            add(workspace, name="   ")
    finally:
        workspace.close()


def test_unknown_unit_and_invalid_date_are_rejected() -> None:
    workspace = SessionWorkspace()
    try:
        with pytest.raises(InventoryInputError, match="无法识别"):
            add(workspace, unit="袋")
        with pytest.raises(InventoryInputError, match="格式不正确"):
            add(workspace, expiration_date="2026-02-30")
    finally:
        workspace.close()


def test_session_a_edit_does_not_affect_session_b() -> None:
    first, second = SessionWorkspace(), SessionWorkspace()
    try:
        add(first)
        update(first, item(first, "chicken_breast")["pantry_item_id"], quantity=300)
        assert len(rows(first)) == 21
        assert len(rows(second)) == 20
        assert item(second, "chicken_breast")["quantity"] == 1500
    finally:
        first.close()
        second.close()


def test_restore_baseline_only_changes_current_session() -> None:
    first, second = SessionWorkspace(), SessionWorkspace()
    try:
        add(first)
        update(first, item(first, "chicken_breast")["pantry_item_id"], quantity=300)
        update(second, item(second, "chicken_breast")["pantry_item_id"], quantity=700)
        first.activate()
        with get_session() as session:
            restore_baseline_inventory(session, first.session_id, DEMO_USER_ID)
        assert len(rows(first)) == 20
        assert item(first, "chicken_breast")["quantity"] == 1500
        assert item(second, "chicken_breast")["quantity"] == 700
    finally:
        first.close()
        second.close()


def test_recommendation_reads_added_custom_food_as_candidate() -> None:
    workspace = SessionWorkspace()
    try:
        result = add(workspace)
        state = proposed(workspace)
        assert any(row["canonical_item_id"] == result["canonical_item_id"] for row in state["eligible_inventory"])
    finally:
        workspace.close()


def test_recommendation_uses_updated_quantity_and_rejects_insufficient_plan() -> None:
    workspace = SessionWorkspace()
    try:
        chicken = item(workspace, "chicken_breast")
        update(workspace, chicken["pantry_item_id"], quantity=100)
        state = proposed(workspace)
        assert next(row for row in state["inventory_snapshot"] if row["canonical_item_id"] == "chicken_breast")["quantity"] == 100
        assert all(
            ingredient["canonical_item_id"] != "chicken_breast"
            for ingredient in state["proposed_plan"]["ingredients"]
        )
    finally:
        workspace.close()


def test_expired_food_is_not_executable_and_near_expiry_is_flagged() -> None:
    workspace = SessionWorkspace()
    try:
        chicken = item(workspace, "chicken_breast")
        update(workspace, chicken["pantry_item_id"], quantity=1500,
               expiration_date=(date.today() - timedelta(days=1)).isoformat())
        state = proposed(workspace)
        assert all(row["canonical_item_id"] != "chicken_breast" for row in state["eligible_inventory"])
        assert all(
            ingredient["canonical_item_id"] != "chicken_breast"
            for ingredient in state["proposed_plan"]["ingredients"]
        )
    finally:
        workspace.close()


def test_inventory_edits_create_audit_records_and_duplicate_request_is_blocked() -> None:
    workspace = SessionWorkspace()
    try:
        add(workspace, request_id="same-request")
        with pytest.raises(InventoryInputError, match="重复提交"):
            add(workspace, name="豆皮", request_id="same-request")
        workspace.activate()
        with get_session() as session:
            audits = list_inventory_audit(session, workspace.session_id)
        assert audits[0]["event_type"] == "inventory_edit_add"
    finally:
        workspace.close()


def test_add_update_delete_and_reset_each_create_audit_event() -> None:
    workspace = SessionWorkspace()
    try:
        result = add(workspace)
        tofu = item(workspace, result["canonical_item_id"])
        update(workspace, tofu["pantry_item_id"], quantity=450)
        delete(workspace, tofu["pantry_item_id"])
        workspace.activate()
        with get_session() as session:
            restore_baseline_inventory(session, workspace.session_id, DEMO_USER_ID)
            event_types = {entry["event_type"] for entry in list_inventory_audit(session, workspace.session_id)}
        assert {
            "inventory_edit_add", "inventory_edit_update", "inventory_edit_delete", "inventory_edit_reset"
        }.issubset(event_types)
    finally:
        workspace.close()
