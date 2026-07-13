from __future__ import annotations

from datetime import date, timedelta

from agent.graph import run_agent
from agent.state import initial_state
from database.models import PantryItem
from database.repositories import get_profile, list_inventory
from database.seed import ALIASES, DEMO_USER_ID, FOODS
from database.session import get_session
from services.alias_mapper import map_alias
from services.inventory_editor import add_inventory_item, soft_delete_inventory_item, update_inventory_item
from services.recipes import load_recipes, rank_recipes
from services.units import is_known_unit
from session_store import SessionWorkspace


MEAT_IDS = {"chicken_breast", "chicken_thigh", "lean_pork", "beef", "shrimp", "fish"}


def inventory(workspace: SessionWorkspace) -> list[dict]:
    workspace.activate()
    with get_session() as session:
        return list_inventory(session, DEMO_USER_ID)


def proposed(workspace: SessionWorkspace, query: str) -> dict:
    workspace.activate()
    return run_agent(initial_state(workspace.session_id, DEMO_USER_ID, query))


def delete_food(workspace: SessionWorkspace, food_id: str) -> None:
    row = next(item for item in inventory(workspace) if item["canonical_item_id"] == food_id)
    workspace.activate()
    with get_session() as session:
        soft_delete_inventory_item(session, workspace.session_id, DEMO_USER_ID, row["pantry_item_id"])


def add_food(workspace: SessionWorkspace, name: str, quantity: float, unit: str = "g") -> dict:
    workspace.activate()
    with get_session() as session:
        return add_inventory_item(
            session, workspace.session_id, DEMO_USER_ID, name=name, quantity=quantity, unit=unit,
            expiration_date=None, location="冷藏"
        )


def recipe_for_plan(plan: dict) -> dict:
    return next(recipe for recipe in load_recipes() if recipe["name"] == plan["title"])


def test_catalog_sizes_match_controlled_scope() -> None:
    assert 40 <= len(FOODS) <= 50
    assert len(ALIASES) >= 70
    assert 25 <= len(load_recipes()) <= 30


def test_recipe_categories_have_expected_counts() -> None:
    recipes = load_recipes()
    assert sum(recipe["meal_type"] == "早餐" for recipe in recipes) == 6
    assert sum(recipe["meal_type"] == "午餐/晚餐" for recipe in recipes) == 18
    assert sum(recipe["meal_type"] == "轻食" for recipe in recipes) == 4


def test_every_recipe_uses_valid_food_ids_units_and_positive_amounts() -> None:
    food_ids = {row[0] for row in FOODS}
    for recipe in load_recipes():
        assert recipe["recipe_id"]
        assert recipe["name"]
        assert recipe["cooking_steps"]
        for ingredient in [*recipe["required_ingredients"], *recipe["pantry_staples"]]:
            assert ingredient["canonical_food_id"] in food_ids
            assert is_known_unit(ingredient["unit"])
            assert ingredient["amount"] > 0
        for optional_id in recipe["optional_ingredients"]:
            assert optional_id in food_ids
        for rule in recipe["substitution_rules"]:
            assert rule["from"] in food_ids
            assert rule["to"] in food_ids


def test_common_aliases_map_to_expected_foods() -> None:
    workspace = SessionWorkspace()
    try:
        workspace.activate()
        with get_session() as session:
            expected = {
                "西红柿": "tomato", "chicken breast": "chicken_breast", "egg": "egg",
                "broccoli": "broccoli", "mushroom": "mushroom", "potato": "potato",
                "sweet potato": "sweet_potato", "noodles": "noodles", "tofu": "firm_tofu",
                "prawns": "shrimp", "yogurt": "plain_yogurt", "oats": "oats",
            }
            for alias, food_id in expected.items():
                assert map_alias(session, alias)["canonical_item_id"] == food_id
    finally:
        workspace.close()


def test_breakfast_request_prioritizes_breakfast_recipe() -> None:
    workspace = SessionWorkspace()
    try:
        plan = proposed(workspace, "请推荐一份简单营养早餐。")
        assert plan["proposed_plan"]["meal_type"] == "早餐"
    finally:
        workspace.close()


def test_high_protein_request_returns_high_protein_tag() -> None:
    workspace = SessionWorkspace()
    try:
        plan = proposed(workspace, "今晚想吃高蛋白、低脂、30分钟以内可以完成的食物。")["proposed_plan"]
        recipe = recipe_for_plan(plan)
        assert "高蛋白" in recipe["tags"]
        assert "低脂" in recipe["tags"]
    finally:
        workspace.close()


def test_vegetarian_request_excludes_meat_and_seafood() -> None:
    workspace = SessionWorkspace()
    try:
        plan = proposed(workspace, "我今天想吃素食。请推荐一份30分钟以内的方案。")["proposed_plan"]
        recipe = recipe_for_plan(plan)
        assert "素食" in recipe["tags"]
        assert not ({item["canonical_item_id"] for item in plan["ingredients"]} & MEAT_IDS)
    finally:
        workspace.close()


def test_allergies_and_avoid_foods_are_hard_filters() -> None:
    workspace = SessionWorkspace()
    try:
        results = rank_recipes(
            {"max_minutes": 30},
            inventory(workspace),
            {"allergies": ["鸡蛋"], "avoid_foods": ["鸡胸肉"], "preferences": []},
        )
        assert results
        blocked = {"egg", "chicken_breast"}
        for result in results:
            used = {item["canonical_item_id"] for item in result["ingredients"]}
            assert not (used & blocked)
    finally:
        workspace.close()


def test_fifteen_minute_request_excludes_long_recipes() -> None:
    workspace = SessionWorkspace()
    try:
        plan = proposed(workspace, "请推荐一道15分钟以内可以完成的快手菜。")["proposed_plan"]
        assert plan["estimated_minutes"] <= 15
    finally:
        workspace.close()


def test_all_major_foods_insufficient_produces_no_executable_plan() -> None:
    workspace = SessionWorkspace()
    try:
        workspace.activate()
        with get_session() as session:
            for row in session.query(PantryItem).filter(PantryItem.user_id == DEMO_USER_ID).all():
                row.quantity = 0
            session.commit()
        state = proposed(workspace, "请推荐一份晚餐。")
        assert not state.get("proposed_plan")
    finally:
        workspace.close()


def test_expiring_tomato_adds_ranking_bonus() -> None:
    workspace = SessionWorkspace()
    try:
        workspace.activate()
        with get_session() as session:
            rows = list_inventory(session, DEMO_USER_ID)
            profile = get_profile(session, DEMO_USER_ID)
        requirements = {
            "query": "请优先使用快过期的食材。", "max_minutes": 30, "meal_type": None,
            "prefer_expiring": True, "high_protein": False, "low_fat": False,
            "vegetarian": False, "home_style": False, "entities": [],
        }
        ranked = rank_recipes(requirements, [row for row in rows if not row["expired"]], profile or {})
        assert "tomato" in {item["canonical_item_id"] for item in ranked[0]["ingredients"]}
        assert any("即将到期" in reason for reason in ranked[0]["reasons"])
    finally:
        workspace.close()


def test_substitution_is_revalidated_and_explained() -> None:
    workspace = SessionWorkspace()
    try:
        delete_food(workspace, "chicken_breast")
        add_food(workspace, "鸡腿肉", 1000)
        plan = proposed(workspace, "今晚想吃高蛋白、低脂、30分钟以内可以完成的食物。")["proposed_plan"]
        assert "chicken_breast" not in {item["canonical_item_id"] for item in plan["ingredients"]}
        if "chicken_thigh" in {item["canonical_item_id"] for item in plan["ingredients"]}:
            assert any("鸡腿肉替代鸡胸肉" in note for note in plan["substitutions"])
        for ingredient in plan["ingredients"]:
            row = next(item for item in inventory(workspace)
                       if item["canonical_item_id"] == ingredient["canonical_item_id"])
            assert ingredient["amount"] <= row["quantity"]
    finally:
        workspace.close()


def test_unknown_custom_food_does_not_create_recipe_or_nutrition() -> None:
    workspace = SessionWorkspace()
    try:
        custom = add_food(workspace, "鲍鱼", 300)
        row = next(item for item in inventory(workspace) if item["canonical_item_id"] == custom["canonical_item_id"])
        plan = proposed(workspace, "请只使用当前演示库存推荐一份饭菜。")["proposed_plan"]
        assert row["nutrition_available"] is False
        assert custom["canonical_item_id"] not in {item["canonical_item_id"] for item in plan["ingredients"]}
    finally:
        workspace.close()


def test_deleting_noodles_removes_noodle_recipes() -> None:
    workspace = SessionWorkspace()
    try:
        delete_food(workspace, "noodles")
        plan = proposed(workspace, "请推荐一份简单营养早餐。")
        assert all(item["canonical_item_id"] != "noodles" for item in plan["proposed_plan"]["ingredients"])
    finally:
        workspace.close()


def test_adding_beef_enables_beef_recipe_candidate() -> None:
    workspace = SessionWorkspace()
    try:
        add_food(workspace, "牛肉", 800)
        plan = proposed(workspace, "今晚想吃牛肉，30分钟以内。")["proposed_plan"]
        assert "beef" in {item["canonical_item_id"] for item in plan["ingredients"]}
        assert plan["title"] in {"青椒牛肉", "洋葱牛肉饭", "番茄牛肉面"}
    finally:
        workspace.close()


def test_tofu_inventory_enables_tofu_recipe() -> None:
    workspace = SessionWorkspace()
    try:
        plan = proposed(workspace, "今晚想吃豆腐做的素食，30分钟以内。")["proposed_plan"]
        assert "firm_tofu" in {item["canonical_item_id"] for item in plan["ingredients"]}
        assert plan["title"] in {"番茄豆腐", "豆腐蔬菜碗", "家常烧豆腐"}
    finally:
        workspace.close()


def test_missing_pantry_staples_do_not_block_main_recipe() -> None:
    workspace = SessionWorkspace()
    try:
        for food_id in ("cooking_oil", "soy_sauce", "salt"):
            delete_food(workspace, food_id)
        plan = proposed(workspace, "请推荐一道30分钟以内的家常晚餐。")["proposed_plan"]
        assert plan["ingredients"]
    finally:
        workspace.close()


def test_two_sessions_can_return_different_results_after_inventory_edit() -> None:
    first, second = SessionWorkspace(), SessionWorkspace()
    try:
        delete_food(first, "chicken_breast")
        first_plan = proposed(first, "今晚想吃高蛋白、低脂、30分钟以内可以完成的食物。")["proposed_plan"]
        second_plan = proposed(second, "今晚想吃高蛋白、低脂、30分钟以内可以完成的食物。")["proposed_plan"]
        assert all(item["canonical_item_id"] != "chicken_breast" for item in first_plan["ingredients"])
        assert any(item["canonical_item_id"] == "chicken_breast" for item in second_plan["ingredients"])
    finally:
        first.close()
        second.close()
