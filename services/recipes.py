from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from database.seed import FOODS
from services.units import convert_amount


PUBLIC_ROOT = Path(__file__).resolve().parents[1]
RECIPE_PATH = PUBLIC_ROOT / "data" / "sample_recipes.json"
FOOD_NAMES = {row[0]: row[1] for row in FOODS}

SCORE_WEIGHTS = {
    "inventory_coverage": 35,
    "meal_type_match": 28,
    "time_match": 18,
    "nutrition_tag_match": 14,
    "preference_match": 6,
    "expiring_food_use": 12,
    "requested_food_match": 35,
    "substitution_penalty": -3,
}


@lru_cache(maxsize=1)
def load_recipes() -> list[dict[str, Any]]:
    return json.loads(RECIPE_PATH.read_text(encoding="utf-8"))


def catalog_counts() -> dict[str, int]:
    recipes = load_recipes()
    return {
        "recipes": len(recipes),
        "breakfast": sum(recipe["meal_type"] == "早餐" for recipe in recipes),
        "main_meals": sum(recipe["meal_type"] == "午餐/晚餐" for recipe in recipes),
        "light_meals": sum(recipe["meal_type"] == "轻食" for recipe in recipes),
    }


def _available(item: dict[str, Any], amount: float, unit: str) -> bool:
    if item.get("expired") or float(item.get("quantity", 0)) <= 0:
        return False
    try:
        return convert_amount(amount, unit, item["unit"]) <= float(item["quantity"]) + 1e-9
    except ValueError:
        return False


def _meal_type_matches(recipe: dict[str, Any], requested: str | None) -> bool:
    if not requested:
        return True
    if requested == "早餐":
        return recipe["meal_type"] == "早餐" or "早餐" in recipe["tags"]
    if requested == "轻食":
        return recipe["meal_type"] == "轻食" or "轻食" in recipe["tags"]
    return requested in recipe["meal_type"] or requested in recipe["tags"]


def rank_recipes(requirements: dict[str, Any], inventory: list[dict[str, Any]],
                 profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Return executable recipes sorted by a documented, deterministic score."""
    allergies = [str(value).strip().lower() for value in profile.get("allergies", []) if str(value).strip()]
    avoid_foods = [str(value).strip().lower() for value in profile.get("avoid_foods", []) if str(value).strip()]
    inventory_by_id = {
        item["canonical_item_id"]: item
        for item in inventory
        if not any(term in item["canonical_name"].lower() for term in [*allergies, *avoid_foods])
    }
    preferences = [str(value).lower() for value in profile.get("preferences", [])]
    requested_ids = {entity["canonical_item_id"] for entity in requirements.get("entities", [])}
    requested_meal = requirements.get("meal_type")
    results: list[dict[str, Any]] = []

    for recipe in load_recipes():
        if recipe["estimated_minutes"] > requirements.get("max_minutes", 30):
            continue
        if requirements.get("vegetarian") and "素食" not in recipe["tags"]:
            continue

        resolved: list[dict[str, Any]] = []
        substitutions: list[str] = []
        missing: list[str] = []
        failed = False
        for required in recipe["required_ingredients"]:
            food_id = required["canonical_food_id"]
            selected_id = food_id
            selected = inventory_by_id.get(food_id)
            if not selected or not _available(selected, required["amount"], required["unit"]):
                selected = None
                if required.get("whether_substitutable"):
                    for rule in recipe.get("substitution_rules", []):
                        if rule["from"] != food_id:
                            continue
                        replacement = inventory_by_id.get(rule["to"])
                        if replacement and _available(replacement, required["amount"], required["unit"]):
                            selected = replacement
                            selected_id = rule["to"]
                            original_name = inventory_by_id.get(food_id, {}).get(
                                "canonical_name", FOOD_NAMES.get(food_id, food_id)
                            )
                            substitutions.append(
                                f"根据当前演示库存，已使用{replacement['canonical_name']}替代{original_name}。"
                            )
                            missing.append(f"原食材 {original_name} 库存不足，已安全替换")
                            break
            if selected is None:
                failed = True
                break
            resolved.append({
                "canonical_item_id": selected_id,
                "display_name": selected["canonical_name"],
                "amount": float(required["amount"]),
                "unit": required["unit"],
                "available_amount": float(selected["quantity"]),
                "inventory_unit": selected["unit"],
                "source": "inventory",
                "confidence": 1.0,
            })
        if failed:
            continue

        staple_missing = []
        for staple in recipe.get("pantry_staples", []):
            row = inventory_by_id.get(staple["canonical_food_id"])
            if not row or not _available(row, staple["amount"], staple["unit"]):
                staple_missing.append(staple["canonical_food_id"])
        if staple_missing:
            missing.append("部分基础调味料未在库存中，演示中按可省略处理")

        score = float(SCORE_WEIGHTS["inventory_coverage"])
        reasons = ["当前所需主要食材均有库存"]
        meal_match = _meal_type_matches(recipe, requested_meal)
        if meal_match and requested_meal:
            score += SCORE_WEIGHTS["meal_type_match"]
            reasons.append(f"符合{requested_meal}场景")
        elif requested_meal:
            score -= SCORE_WEIGHTS["meal_type_match"] / 2

        score += SCORE_WEIGHTS["time_match"]
        reasons.append(f"符合{requirements.get('max_minutes', 30)}分钟以内的要求")

        tag_matches = 0
        if requirements.get("high_protein") and "高蛋白" in recipe["tags"]:
            tag_matches += 1
            reasons.append("该方案属于高蛋白演示菜谱")
        if requirements.get("low_fat") and "低脂" in recipe["tags"]:
            tag_matches += 1
            reasons.append("该方案符合低脂标签")
        if requirements.get("vegetarian") and "素食" in recipe["tags"]:
            tag_matches += 1
            reasons.append("该方案不使用肉类或海鲜")
        if requirements.get("home_style") and "家常" in recipe["tags"]:
            tag_matches += 1
            reasons.append("该方案属于快手家常菜")
        score += tag_matches * SCORE_WEIGHTS["nutrition_tag_match"]

        recipe_text = " ".join([recipe["name"], *recipe["tags"]]).lower()
        preference_hits = sum(pref in recipe_text for pref in preferences)
        if preference_hits:
            score += min(preference_hits, 2) * SCORE_WEIGHTS["preference_match"]
            reasons.append("与演示饮食偏好相符")

        used_ids = {item["canonical_item_id"] for item in resolved}
        entity_hits = len(used_ids & requested_ids)
        if entity_hits:
            score += entity_hits * SCORE_WEIGHTS["requested_food_match"]
            reasons.append("包含需求中提到的食材")

        expiring_names = []
        for ingredient in resolved:
            row = inventory_by_id[ingredient["canonical_item_id"]]
            expiration = row.get("expiration_date")
            if expiration and 0 <= (expiration - date.today()).days <= 3:
                expiring_names.append(row["canonical_name"])
        if expiring_names:
            bonus = (
                SCORE_WEIGHTS["expiring_food_use"]
                * len(expiring_names)
                * (2 if requirements.get("prefer_expiring") else 1)
            )
            score += bonus
            reasons.append(f"{('、'.join(expiring_names))}即将到期，因此优先推荐使用")

        score += len(substitutions) * SCORE_WEIGHTS["substitution_penalty"]
        results.append({
            "score": round(score, 2),
            "recipe": recipe,
            "ingredients": resolved,
            "reasons": reasons[:5],
            "substitutions": substitutions,
            "missing_ingredients": missing,
        })

    return sorted(results, key=lambda item: (-item["score"], item["recipe"]["estimated_minutes"], item["recipe"]["recipe_id"]))
