from __future__ import annotations

from datetime import date
from typing import Any

from schemas.meal_plan import MealPlan
from services.units import convert_amount, is_known_unit
from agent.nodes.shared import update_with_audit


def eligible_inventory(profile: dict[str, Any], inventory: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    allowed, warnings = [], []
    allergies = [str(x).lower() for x in profile.get("allergies", [])]
    avoids = [str(x).lower() for x in profile.get("avoid_foods", [])]
    for item in inventory:
        name = item["canonical_name"].lower()
        if item.get("expired"):
            warnings.append(f"已排除过期食材：{item['canonical_name']}"); continue
        if item["quantity"] <= 0:
            warnings.append(f"已排除零库存食材：{item['canonical_name']}"); continue
        if not is_known_unit(item["unit"]):
            warnings.append(f"已排除单位无法识别食材：{item['canonical_name']}"); continue
        if any(a in name or (a == "花生" and "花生" in name) for a in allergies):
            warnings.append(f"已排除过敏原：{item['canonical_name']}"); continue
        if any(a in name for a in avoids):
            warnings.append(f"已排除忌口食材：{item['canonical_name']}"); continue
        allowed.append(item)
    return allowed, warnings


def validate_plan(plan: MealPlan, profile: dict[str, Any], inventory: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    allowed, _ = eligible_inventory(profile, inventory)
    by_id = {item["canonical_item_id"]: item for item in allowed}
    allergies = [str(x).lower() for x in profile.get("allergies", [])]
    avoids = [str(x).lower() for x in profile.get("avoid_foods", [])]
    for usage in plan.ingredients:
        item = by_id.get(usage.canonical_item_id)
        if not item:
            errors.append(f"食材不在可执行库存中：{usage.display_name}")
            continue
        name = item["canonical_name"].lower()
        if any(a in name for a in allergies): errors.append(f"过敏冲突：{usage.display_name}")
        if any(a in name for a in avoids): errors.append(f"忌口冲突：{usage.display_name}")
        try:
            requested = convert_amount(usage.amount, usage.unit, item["unit"])
            if requested > item["quantity"] + 1e-9:
                errors.append(f"库存不足：{usage.display_name}")
        except ValueError:
            errors.append(f"单位无法换算：{usage.display_name}")
    if not 150 <= plan.calories_kcal <= 1500:
        errors.append("营养估算热量不在合理范围")
    if plan.protein_g < 0 or plan.fat_g < 0 or plan.carbs_g < 0:
        errors.append("营养估算不能为负数")
    return errors


def deterministic_guard(state: dict) -> dict:
    allowed, warnings = eligible_inventory(state["user_profile"], state["inventory_snapshot"])
    return update_with_audit(state, "deterministic_guard", f"确定性过滤后保留 {len(allowed)} 项库存",
                             eligible_inventory=allowed, warnings=warnings)
