from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import AuditLog, InventoryTransaction, InventoryTransactionLine, PantryItem
from services.units import convert_amount


class InventoryTransactionError(ValueError):
    pass


def execute_deduction(session: Session, user_id: str, meal_plan_id: str, usages: list[dict]) -> str:
    """Re-read every row and atomically deduct only after all rows can satisfy usage."""
    if not usages:
        raise InventoryTransactionError("没有可扣减的食材")
    if session.in_transaction():
        session.commit()
    transaction_id = str(uuid4())
    try:
        with session.begin():
            resolved: list[tuple[PantryItem, float, dict]] = []
            for usage in usages:
                item = session.scalar(select(PantryItem).where(PantryItem.user_id == user_id,
                                      PantryItem.canonical_food_id == usage["canonical_item_id"],
                                      PantryItem.active.is_(True)).with_for_update())
                if not item:
                    raise InventoryTransactionError(f"库存中不存在: {usage['canonical_item_id']}")
                if item.expiration_date and item.expiration_date < date.today():
                    raise InventoryTransactionError(f"食材已经过期: {usage['canonical_item_id']}")
                try:
                    change = convert_amount(float(usage["amount"]), usage["unit"], item.unit)
                except ValueError as exc:
                    raise InventoryTransactionError(str(exc)) from exc
                if change <= 0 or item.quantity + 1e-9 < change:
                    raise InventoryTransactionError(f"库存不足: {usage['canonical_item_id']}")
                resolved.append((item, change, usage))
            tx = InventoryTransaction(id=transaction_id, user_id=user_id, meal_plan_id=meal_plan_id,
                                      transaction_type="deduction", status="completed")
            session.add(tx)
            for item, change, _ in resolved:
                before = item.quantity
                item.quantity = round(before - change, 4)
                item.version += 1
                session.add(InventoryTransactionLine(transaction_id=transaction_id, pantry_item_id=item.id,
                            quantity_before=before, quantity_change=-change, quantity_after=item.quantity, unit=item.unit))
        return transaction_id
    except Exception:
        session.rollback()
        raise


def undo_transaction(session: Session, transaction_id: str, session_id: str = "manual") -> None:
    if session.in_transaction():
        session.commit()
    with session.begin():
        tx = session.get(InventoryTransaction, transaction_id)
        if not tx or tx.status != "completed" or tx.reversed_at:
            raise InventoryTransactionError("该库存事务不存在或已经撤销")
        lines = session.scalars(select(InventoryTransactionLine).where(
                              InventoryTransactionLine.transaction_id == transaction_id)).all()
        for line in lines:
            item = session.get(PantryItem, line.pantry_item_id)
            if not item:
                raise InventoryTransactionError("撤销失败：库存行不存在")
            item.quantity = round(item.quantity - line.quantity_change, 4)
            item.version += 1
        tx.status = "reversed"
        tx.reversed_at = datetime.utcnow()
        session.add(AuditLog(session_id=session_id, user_id=tx.user_id, event_type="inventory_undo",
                             node_name="undo_transaction", payload_json=f'{{"transaction_id": "{transaction_id}"}}'))
