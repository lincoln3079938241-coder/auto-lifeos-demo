from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import CanonicalFood, FoodAlias


def normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def map_alias(session: Session, value: str) -> dict[str, str | None]:
    normalized = normalize_text(value)
    alias = session.scalar(select(FoodAlias).where(FoodAlias.alias == normalized))
    if alias:
        food = session.get(CanonicalFood, alias.canonical_food_id)
        return {"input": value, "canonical_item_id": food.id, "canonical_name": food.canonical_name, "status": "mapped"}
    food = session.scalar(select(CanonicalFood).where(CanonicalFood.canonical_name == value.strip()))
    if food:
        return {"input": value, "canonical_item_id": food.id, "canonical_name": food.canonical_name, "status": "mapped"}
    return {"input": value, "canonical_item_id": None, "canonical_name": None, "status": "unknown"}

