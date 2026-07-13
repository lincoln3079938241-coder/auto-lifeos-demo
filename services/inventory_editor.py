from __future__ import annotations

import json
import math
from datetime import date, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.models import AuditLog, CanonicalFood, PantryItem
from database.seed import baseline_pantry
from services.alias_mapper import map_alias, normalize_text
from services.units import convert_amount, is_known_unit


MAX_INVENTORY_QUANTITY = 1_000_000.0


class InventoryInputError(ValueError):
    """A user-safe validation error for inventory editing."""


class ExistingInventoryItem(InventoryInputError):
    def __init__(self, canonical_name: str, pantry_item_id: int) -> None:
        super().__init__(f"库存中已经存在{canonical_name}")
        self.canonical_name = canonical_name
        self.pantry_item_id = pantry_item_id


def parse_quantity(value: Any) -> float:
    if isinstance(value, bool):
        raise InventoryInputError("请输入有效的数字数量")
    try:
        quantity = float(value)
    except (TypeError, ValueError) as exc:
        raise InventoryInputError("请输入有效的数字数量") from exc
    if not math.isfinite(quantity):
        raise InventoryInputError("请输入有效的数字数量")
    if quantity <= 0:
        raise InventoryInputError("数量必须大于 0")
    if quantity > MAX_INVENTORY_QUANTITY:
        raise InventoryInputError("数量过大，请输入不超过 1000000 的数值")
    return round(quantity, 4)


def parse_unit(value: str) -> str:
    unit = str(value or "").strip().lower()
    if not is_known_unit(unit):
        raise InventoryInputError("无法识别这个单位，请使用 g、kg、ml、l 或个")
    return unit


def parse_expiration(value: date | str | None) -> date | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise InventoryInputError("保质期格式不正确，请使用 YYYY-MM-DD") from exc


def _validate_name(value: str) -> str:
    name = " ".join(str(value or "").strip().split())
    if not name:
        raise InventoryInputError("请填写食材名称")
    if len(name) > 100:
        raise InventoryInputError("食材名称过长，请控制在 100 个字以内")
    return name


def _validate_location(value: str) -> str:
    location = " ".join(str(value or "").strip().split()) or "厨房"
    if len(location) > 80:
        raise InventoryInputError("存放位置过长，请控制在 80 个字以内")
    return location


def _ensure_unique_request(session: Session, session_id: str, request_id: str | None) -> None:
    if not request_id:
        return
    existing = session.scalar(
        select(AuditLog.id).where(
            AuditLog.session_id == session_id,
            AuditLog.event_type.like("inventory_edit_%"),
            AuditLog.payload_json.like(f'%"request_id": "{request_id}"%'),
        )
    )
    if existing:
        raise InventoryInputError("请勿重复提交同一次操作")


def _audit(session: Session, session_id: str, user_id: str, event_type: str,
           payload: dict[str, Any], request_id: str | None) -> None:
    data = {**payload, "request_id": request_id or str(uuid4())}
    session.add(
        AuditLog(
            session_id=session_id,
            user_id=user_id,
            event_type=event_type,
            node_name="inventory_editor",
            payload_json=json.dumps(data, ensure_ascii=False, default=str),
        )
    )


def _food_for_name(session: Session, name: str, unit: str) -> tuple[CanonicalFood, bool]:
    mapped = map_alias(session, name)
    if mapped["canonical_item_id"]:
        food = session.get(CanonicalFood, mapped["canonical_item_id"])
        if food is None:
            raise InventoryInputError("暂时无法识别这个食材，请稍后重试")
        return food, False

    normalized = normalize_text(name)
    existing = session.scalar(
        select(CanonicalFood).where(func.lower(CanonicalFood.canonical_name) == normalized)
    )
    if existing:
        return existing, bool(existing.is_custom)

    food = CanonicalFood(
        id=f"custom_{uuid4().hex}",
        canonical_name=name,
        category="自定义",
        default_unit=unit,
        calories_per_100g=None,
        protein_per_100g=None,
        carbs_per_100g=None,
        fat_per_100g=None,
        is_custom=True,
    )
    session.add(food)
    session.flush()
    return food, True


def add_inventory_item(session: Session, session_id: str, user_id: str, *, name: str,
                       quantity: Any, unit: str, expiration_date: date | str | None,
                       location: str, merge_existing: bool = False,
                       request_id: str | None = None) -> dict[str, Any]:
    _ensure_unique_request(session, session_id, request_id)
    safe_name = _validate_name(name)
    safe_quantity = parse_quantity(quantity)
    safe_unit = parse_unit(unit)
    safe_expiration = parse_expiration(expiration_date)
    safe_location = _validate_location(location)
    food, is_custom = _food_for_name(session, safe_name, safe_unit)

    item = session.scalar(
        select(PantryItem)
        .where(PantryItem.user_id == user_id, PantryItem.canonical_food_id == food.id)
        .order_by(PantryItem.id.desc())
    )
    if item and item.active and not merge_existing:
        session.rollback()
        raise ExistingInventoryItem(food.canonical_name, item.id)

    if item and item.active:
        try:
            addition = convert_amount(safe_quantity, safe_unit, item.unit)
        except ValueError as exc:
            session.rollback()
            raise InventoryInputError("新增单位与现有库存不一致，请先修改现有食材单位") from exc
        before = item.quantity
        merged = parse_quantity(before + addition)
        item.quantity = merged
        item.version += 1
        item.updated_at = datetime.utcnow()
        action = "merge"
        payload = {
            "pantry_item_id": item.id,
            "food_name": food.canonical_name,
            "quantity_before": before,
            "quantity_added": addition,
            "quantity_after": merged,
            "unit": item.unit,
        }
    elif item:
        item.quantity = safe_quantity
        item.unit = safe_unit
        item.expiration_date = safe_expiration
        item.location = safe_location
        item.active = True
        item.deleted_at = None
        item.version += 1
        action = "restore"
        payload = {"pantry_item_id": item.id, "food_name": food.canonical_name,
                   "quantity_after": safe_quantity, "unit": safe_unit}
    else:
        item = PantryItem(
            user_id=user_id,
            canonical_food_id=food.id,
            quantity=safe_quantity,
            unit=safe_unit,
            expiration_date=safe_expiration,
            location=safe_location,
            active=True,
        )
        session.add(item)
        session.flush()
        action = "add"
        payload = {"pantry_item_id": item.id, "food_name": food.canonical_name,
                   "quantity_after": safe_quantity, "unit": safe_unit}

    _audit(session, session_id, user_id, f"inventory_edit_{action}", payload, request_id)
    session.commit()
    return {
        "pantry_item_id": item.id,
        "canonical_item_id": food.id,
        "canonical_name": food.canonical_name,
        "quantity": item.quantity,
        "unit": item.unit,
        "is_custom": is_custom,
        "nutrition_available": not is_custom,
        "action": action,
    }


def update_inventory_item(session: Session, session_id: str, user_id: str, pantry_item_id: int, *,
                          quantity: Any, unit: str, expiration_date: date | str | None,
                          location: str, request_id: str | None = None) -> dict[str, Any]:
    _ensure_unique_request(session, session_id, request_id)
    safe_quantity = parse_quantity(quantity)
    safe_unit = parse_unit(unit)
    safe_expiration = parse_expiration(expiration_date)
    safe_location = _validate_location(location)
    item = session.get(PantryItem, pantry_item_id)
    if not item or item.user_id != user_id or not item.active:
        raise InventoryInputError("这个食材已经不存在，请刷新后重试")
    food = session.get(CanonicalFood, item.canonical_food_id)
    before = {"quantity": item.quantity, "unit": item.unit,
              "expiration_date": item.expiration_date, "location": item.location}
    item.quantity = safe_quantity
    item.unit = safe_unit
    item.expiration_date = safe_expiration
    item.location = safe_location
    item.version += 1
    _audit(session, session_id, user_id, "inventory_edit_update", {
        "pantry_item_id": item.id,
        "food_name": food.canonical_name if food else "食材",
        "before": before,
        "after": {"quantity": safe_quantity, "unit": safe_unit,
                  "expiration_date": safe_expiration, "location": safe_location},
    }, request_id)
    session.commit()
    return {"pantry_item_id": item.id, "quantity": item.quantity, "unit": item.unit}


def soft_delete_inventory_item(session: Session, session_id: str, user_id: str, pantry_item_id: int,
                               request_id: str | None = None) -> None:
    _ensure_unique_request(session, session_id, request_id)
    item = session.get(PantryItem, pantry_item_id)
    if not item or item.user_id != user_id or not item.active:
        raise InventoryInputError("这个食材已经删除，无需重复操作")
    food = session.get(CanonicalFood, item.canonical_food_id)
    item.active = False
    item.deleted_at = datetime.utcnow()
    item.version += 1
    _audit(session, session_id, user_id, "inventory_edit_delete", {
        "pantry_item_id": item.id,
        "food_name": food.canonical_name if food else "食材",
        "quantity": item.quantity,
        "unit": item.unit,
    }, request_id)
    session.commit()


def restore_baseline_inventory(session: Session, session_id: str, user_id: str,
                               request_id: str | None = None) -> None:
    _ensure_unique_request(session, session_id, request_id)
    baseline = {food_id: (quantity, unit, expiration, location)
                for food_id, quantity, unit, expiration, location in baseline_pantry()}
    rows = session.scalars(select(PantryItem).where(PantryItem.user_id == user_id)).all()
    by_food = {item.canonical_food_id: item for item in rows}
    for item in rows:
        if item.canonical_food_id not in baseline and item.active:
            item.active = False
            item.deleted_at = datetime.utcnow()
            item.version += 1
    for food_id, (quantity, unit, expiration, location) in baseline.items():
        item = by_food.get(food_id)
        if item:
            item.quantity = quantity
            item.unit = unit
            item.expiration_date = expiration
            item.location = location
            item.active = True
            item.deleted_at = None
            item.version += 1
        else:
            session.add(PantryItem(user_id=user_id, canonical_food_id=food_id, quantity=quantity,
                                   unit=unit, expiration_date=expiration, location=location, active=True))
    _audit(session, session_id, user_id, "inventory_edit_reset", {
        "baseline_item_count": len(baseline),
    }, request_id)
    session.commit()


def inventory_status(item: dict[str, Any], today: date | None = None) -> str:
    current_date = today or date.today()
    expiration = item.get("expiration_date")
    if expiration and expiration < current_date:
        return "已过期"
    if not item.get("nutrition_available", True):
        return "营养数据暂缺"
    if expiration and 0 <= (expiration - current_date).days <= 3:
        return "即将过期"
    unit = str(item.get("unit", "")).lower()
    quantity = float(item.get("quantity", 0))
    low = quantity <= 2 if unit in {"个", "piece"} else quantity <= 200
    return "数量较少" if low else "库存充足"
