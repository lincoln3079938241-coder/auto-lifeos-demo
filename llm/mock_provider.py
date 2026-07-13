from __future__ import annotations

from uuid import uuid4
from typing import Any

from llm.base import MealPlanProvider
from schemas.meal_plan import IngredientUsage, MealPlan
from services.nutrition import estimate_nutrition
from services.recipes import rank_recipes


class MockProvider(MealPlanProvider):
    """Dynamic rule-based generator, intentionally producing the same contract as an LLM."""
    name = "mock"

    @staticmethod
    def adversarial_test_outputs() -> list[dict[str, Any]]:
        """Raw, intentionally invalid candidates for guardrail demonstrations/tests; never executable plans."""
        return [
            {"case": "peanut_allergy", "food_id": "peanut_butter", "amount": 20, "unit": "g"},
            {"case": "over_inventory", "food_id": "chicken_breast", "amount": 99999, "unit": "g"},
            {"case": "hallucinated_food", "food_id": "salmon", "amount": 150, "unit": "g"},
            {"case": "expired_food", "food_id": "yogurt", "amount": 1, "unit": "个"},
            {"case": "negative_amount", "food_id": "oats", "amount": -30, "unit": "g"},
            {"case": "unknown_unit", "food_id": "oats", "amount": 30, "unit": "勺"},
        ]

    def generate(self, requirements: dict[str, Any], inventory: list[dict[str, Any]],
                 evidence: list[dict[str, Any]], profile: dict[str, Any]) -> MealPlan:
        candidates = rank_recipes(requirements, inventory, profile)
        if candidates:
            selected = candidates[0]
            recipe = selected["recipe"]
            ingredients = [IngredientUsage.model_validate(item) for item in selected["ingredients"]]
            ingredient_dicts = [item.model_dump() for item in ingredients]
            nutrition = estimate_nutrition(ingredient_dicts, inventory)
            evidence_ids = [item["id"] for item in evidence]
            selected_ids = {item["canonical_item_id"] for item in ingredient_dicts}
            selected_inventory = [item for item in inventory if item["canonical_item_id"] in selected_ids]
            warnings = ["营养数据仅为演示估算，不构成医疗或个性化营养建议"]
            if any(not item.get("nutrition_available", True) for item in selected_inventory):
                warnings.append("部分食材营养数据暂缺，营养估算可能不完整")
            return MealPlan(
                plan_id=str(uuid4()), title=recipe["name"], description=recipe["description"],
                meal_type=recipe["meal_type"], difficulty=recipe["difficulty"], servings=recipe["servings"],
                estimated_minutes=recipe["estimated_minutes"], calories_kcal=nutrition["calories_kcal"],
                protein_g=nutrition["protein_g"], carbs_g=nutrition["carbs_g"], fat_g=nutrition["fat_g"],
                ingredients=ingredients, steps=recipe["cooking_steps"], reasons=selected["reasons"],
                warnings=warnings, substitutions=selected["substitutions"],
                missing_ingredients=selected["missing_ingredients"], retrieved_evidence_ids=evidence_ids,
            )
        raise ValueError("没有满足库存、时间与饮食限制的可执行方案")
