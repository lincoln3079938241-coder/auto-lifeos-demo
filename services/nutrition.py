from __future__ import annotations

from typing import Any

from services.units import convert_amount


def estimate_nutrition(ingredients: list[dict[str, Any]], inventory: list[dict[str, Any]]) -> dict[str, float]:
    by_id = {row["canonical_item_id"]: row for row in inventory}
    totals = {"calories_kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
    for ingredient in ingredients:
        item = by_id.get(ingredient["canonical_item_id"])
        if not item:
            continue
        if item["unit"] not in {"g", "kg"}:
            # Count-based packaged nutrition is modeled per item in the synthetic seed.
            grams = ingredient["amount"] * 100 if item["unit"] in {"个", "piece"} else ingredient["amount"]
        else:
            grams = convert_amount(ingredient["amount"], ingredient["unit"], "g")
        ratio = grams / 100
        totals["calories_kcal"] += item["calories_per_100g"] * ratio
        totals["protein_g"] += item["protein_per_100g"] * ratio
        totals["carbs_g"] += item["carbs_per_100g"] * ratio
        totals["fat_g"] += item["fat_per_100g"] * ratio
    return {key: round(value, 1) for key, value in totals.items()}

