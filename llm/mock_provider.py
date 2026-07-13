from __future__ import annotations

from uuid import uuid4
from typing import Any
from datetime import date

from llm.base import MealPlanProvider
from schemas.meal_plan import IngredientUsage, MealPlan
from services.nutrition import estimate_nutrition


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

    def _ingredient(self, inventory: list[dict], food_id: str, amount: float) -> IngredientUsage | None:
        item = next((x for x in inventory if x["canonical_item_id"] == food_id), None)
        if not item or item["quantity"] < amount:
            return None
        return IngredientUsage(canonical_item_id=food_id, display_name=item["canonical_name"], amount=amount,
                               unit=item["unit"], available_amount=item["quantity"], inventory_unit=item["unit"],
                               source="inventory", confidence=1.0)

    def generate(self, requirements: dict[str, Any], inventory: list[dict[str, Any]],
                 evidence: list[dict[str, Any]], profile: dict[str, Any]) -> MealPlan:
        query = requirements.get("query", "")
        vegetarian = requirements.get("vegetarian", False)
        wants_breakfast = any(x in query.lower() for x in ["早餐", "早饭", "燕麦", "oat"])
        candidates = []
        if not vegetarian and not wants_breakfast:
            candidates = [
                ("番茄鸡胸饭", "高蛋白、低脂的快手晚餐。", 20, [("chicken_breast", 180), ("tomato", 200), ("rice", 150)],
                 ["鸡胸肉切片煎熟。", "加入番茄快速翻炒。", "配热米饭装盘。"]),
                ("西兰花鸡胸饭", "鸡胸肉配西兰花，蛋白质充足。", 25, [("chicken_breast", 200), ("broccoli", 200), ("rice", 150)],
                 ["煎熟鸡胸肉。", "西兰花焯水后翻炒。", "搭配米饭即可。"]),
            ]
        if vegetarian or wants_breakfast:
            candidates = [("鸡蛋燕麦碗", "适合快速准备的均衡早餐。", 10, [("egg", 2), ("oats", 60), ("milk", 200)],
                           ["燕麦加入牛奶加热。", "同时煮或煎鸡蛋。", "组合装碗即可。"]), *candidates]
        max_minutes = requirements.get("max_minutes", 30)
        for title, description, minutes, rows, steps in candidates:
            if minutes > max_minutes:
                continue
            ingredients = [self._ingredient(inventory, food_id, amount) for food_id, amount in rows]
            if all(ingredients):
                ingredient_dicts = [x.model_dump() for x in ingredients if x]
                nutrition = estimate_nutrition(ingredient_dicts, inventory)
                evidence_ids = [item["id"] for item in evidence]
                selected_ids = {item["canonical_item_id"] for item in ingredient_dicts}
                selected_inventory = [item for item in inventory if item["canonical_item_id"] in selected_ids]
                warnings = ["一般饮食信息，不构成医疗建议"]
                if any(not item.get("nutrition_available", True) for item in selected_inventory):
                    warnings.append("部分食材营养数据暂缺，营养估算可能不完整")
                if any(
                    item.get("expiration_date")
                    and 0 <= (item["expiration_date"] - date.today()).days <= 3
                    for item in selected_inventory
                ):
                    warnings.append("方案包含即将过期的演示食材，请在保质期内使用")
                return MealPlan(plan_id=str(uuid4()), title=title, description=description, estimated_minutes=minutes,
                                calories_kcal=nutrition["calories_kcal"], protein_g=nutrition["protein_g"],
                                carbs_g=nutrition["carbs_g"], fat_g=nutrition["fat_g"], ingredients=ingredients, steps=steps,
                                reasons=["仅使用当前有效库存", "遵循已知过敏与忌口限制", "满足快速烹饪偏好"],
                                warnings=warnings, retrieved_evidence_ids=evidence_ids)
        raise ValueError("没有满足库存、时间与饮食限制的可执行方案")
