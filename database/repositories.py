from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import (AuditLog, CanonicalFood, DietRecord, FoodAlias, InventoryTransaction,
                             InventoryTransactionLine, MealPlanRecord, PantryItem, PrivateKnowledge, UserProfile)


def get_profile(session: Session, user_id: str) -> dict[str, Any] | None:
    row = session.get(UserProfile, user_id)
    if not row:
        return None
    return {"user_id": row.user_id, "height_cm": row.height_cm, "weight_kg": row.weight_kg,
            "goal": row.goal, "daily_calorie_min": row.daily_calorie_min,
            "daily_calorie_max": row.daily_calorie_max,
            "allergies": json.loads(row.allergies_json), "avoid_foods": json.loads(row.avoid_foods_json),
            "preferences": json.loads(row.preferences_json)}


def update_profile(session: Session, user_id: str, **values: Any) -> None:
    row = session.get(UserProfile, user_id)
    if not row:
        raise ValueError("用户档案不存在")
    for json_key, model_key in (("allergies", "allergies_json"), ("avoid_foods", "avoid_foods_json"), ("preferences", "preferences_json")):
        if json_key in values:
            setattr(row, model_key, json.dumps(values.pop(json_key), ensure_ascii=False))
    for key, value in values.items():
        if hasattr(row, key):
            setattr(row, key, value)
    session.commit()


def list_inventory(session: Session, user_id: str, include_expired: bool = True,
                   include_inactive: bool = False) -> list[dict[str, Any]]:
    statement = (
        select(PantryItem, CanonicalFood)
        .join(CanonicalFood, PantryItem.canonical_food_id == CanonicalFood.id)
        .where(PantryItem.user_id == user_id)
        .order_by(CanonicalFood.canonical_name)
    )
    if not include_inactive:
        statement = statement.where(PantryItem.active.is_(True))
    rows = session.execute(statement).all()
    today = date.today()
    result = []
    for item, food in rows:
        expired = bool(item.expiration_date and item.expiration_date < today)
        if include_expired or not expired:
            nutrition_available = all(value is not None for value in (
                food.calories_per_100g, food.protein_per_100g, food.carbs_per_100g, food.fat_per_100g
            ))
            result.append({"pantry_item_id": item.id, "canonical_item_id": food.id, "canonical_name": food.canonical_name,
                           "quantity": item.quantity, "unit": item.unit, "expiration_date": item.expiration_date,
                           "location": item.location, "version": item.version, "expired": expired,
                           "active": item.active, "deleted_at": item.deleted_at, "is_custom": food.is_custom,
                           "nutrition_available": nutrition_available,
                           "calories_per_100g": food.calories_per_100g, "protein_per_100g": food.protein_per_100g,
                           "carbs_per_100g": food.carbs_per_100g, "fat_per_100g": food.fat_per_100g})
    return result


def list_foods(session: Session) -> list[CanonicalFood]:
    return session.scalars(select(CanonicalFood).order_by(CanonicalFood.canonical_name)).all()


def add_pantry_item(session: Session, user_id: str, canonical_food_id: str, quantity: float, unit: str,
                    expiration_date: date | None, location: str) -> None:
    if quantity <= 0:
        raise ValueError("库存数量必须为正数")
    session.add(PantryItem(user_id=user_id, canonical_food_id=canonical_food_id, quantity=quantity, unit=unit,
                           expiration_date=expiration_date, location=location))
    session.commit()


def update_pantry_quantity(session: Session, pantry_item_id: int, quantity: float, location: str | None = None) -> None:
    item = session.get(PantryItem, pantry_item_id)
    if not item or quantity < 0:
        raise ValueError("库存条目不存在或数量无效")
    item.quantity = quantity
    item.version += 1
    if location: item.location = location
    session.commit()


def list_knowledge(session: Session, user_id: str) -> list[dict[str, Any]]:
    rows = session.scalars(select(PrivateKnowledge).where(PrivateKnowledge.user_id == user_id)).all()
    return [{"id": r.id, "title": r.title, "content": r.content, "source_type": r.source_type, "tags": r.tags} for r in rows]


def add_knowledge(session: Session, user_id: str, title: str, content: str, source_type: str = "manual", tags: str = "") -> int:
    row = PrivateKnowledge(user_id=user_id, title=title, content=content, source_type=source_type, tags=tags)
    session.add(row); session.commit(); return row.id


def delete_knowledge(session: Session, knowledge_id: int) -> None:
    row = session.get(PrivateKnowledge, knowledge_id)
    if row:
        session.delete(row); session.commit()


def save_meal_plan(session: Session, user_id: str, query: str, plan_id: str, plan_json: str, status: str = "proposed") -> None:
    row = session.get(MealPlanRecord, plan_id)
    if row:
        row.status = status; row.plan_json = plan_json
    else:
        session.add(MealPlanRecord(id=plan_id, user_id=user_id, query=query, plan_json=plan_json, status=status))
    session.commit()


def save_diet_record(session: Session, user_id: str, plan_id: str, consumption: list[dict[str, Any]], nutrition: dict[str, Any]) -> None:
    session.add(DietRecord(user_id=user_id, meal_plan_id=plan_id, consumption_json=json.dumps(consumption, ensure_ascii=False),
                           estimated_nutrition_json=json.dumps(nutrition, ensure_ascii=False)))
    session.commit()


def append_audit(session: Session, session_id: str, user_id: str, event_type: str, node_name: str, payload: Any) -> None:
    session.add(AuditLog(session_id=session_id, user_id=user_id, event_type=event_type, node_name=node_name,
                         payload_json=json.dumps(payload, ensure_ascii=False, default=str)))
    session.commit()


def list_audit(session: Session, session_id: str) -> list[dict[str, Any]]:
    rows = session.scalars(select(AuditLog).where(AuditLog.session_id == session_id).order_by(AuditLog.id)).all()
    return [{"node_name": r.node_name, "event_type": r.event_type, "payload": json.loads(r.payload_json),
             "created_at": r.created_at} for r in rows]


def list_inventory_audit(session: Session, session_id: str) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(AuditLog)
        .where(AuditLog.session_id == session_id, AuditLog.event_type.like("inventory_edit_%"))
        .order_by(AuditLog.id.desc())
    ).all()
    return [
        {
            "event_type": row.event_type,
            "payload": json.loads(row.payload_json),
            "created_at": row.created_at,
        }
        for row in rows
    ]


def latest_executable_transaction(session: Session, user_id: str) -> InventoryTransaction | None:
    return session.scalars(select(InventoryTransaction).where(InventoryTransaction.user_id == user_id,
                          InventoryTransaction.status == "completed").order_by(InventoryTransaction.created_at.desc())).first()


def list_inventory_transaction_lines(session: Session, user_id: str, limit: int = 30) -> list[dict[str, Any]]:
    rows = session.execute(
        select(InventoryTransaction, InventoryTransactionLine, PantryItem, CanonicalFood)
        .join(InventoryTransactionLine, InventoryTransactionLine.transaction_id == InventoryTransaction.id)
        .join(PantryItem, PantryItem.id == InventoryTransactionLine.pantry_item_id)
        .join(CanonicalFood, CanonicalFood.id == PantryItem.canonical_food_id)
        .where(InventoryTransaction.user_id == user_id)
        .order_by(InventoryTransaction.created_at.desc(), InventoryTransactionLine.id)
        .limit(limit)
    ).all()
    return [{"transaction_id": tx.id, "status": tx.status, "created_at": tx.created_at,
             "canonical_name": food.canonical_name, "quantity_before": line.quantity_before,
             "quantity_change": line.quantity_change, "quantity_after": line.quantity_after,
             "unit": line.unit} for tx, line, _, food in rows]
