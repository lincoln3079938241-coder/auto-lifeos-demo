from __future__ import annotations

from datetime import date, datetime
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserProfile(Base):
    __tablename__ = "user_profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    height_cm: Mapped[float] = mapped_column(Float)
    weight_kg: Mapped[float] = mapped_column(Float)
    goal: Mapped[str] = mapped_column(String(300))
    daily_calorie_min: Mapped[int] = mapped_column(Integer)
    daily_calorie_max: Mapped[int] = mapped_column(Integer)
    allergies_json: Mapped[str] = mapped_column(Text, default="[]")
    avoid_foods_json: Mapped[str] = mapped_column(Text, default="[]")
    preferences_json: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CanonicalFood(Base):
    __tablename__ = "canonical_foods"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(100), unique=True)
    category: Mapped[str] = mapped_column(String(50))
    default_unit: Mapped[str] = mapped_column(String(20))
    calories_per_100g: Mapped[float] = mapped_column(Float)
    protein_per_100g: Mapped[float] = mapped_column(Float)
    carbs_per_100g: Mapped[float] = mapped_column(Float)
    fat_per_100g: Mapped[float] = mapped_column(Float)


class FoodAlias(Base):
    __tablename__ = "food_aliases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alias: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    canonical_food_id: Mapped[str] = mapped_column(ForeignKey("canonical_foods.id"))


class PantryItem(Base):
    __tablename__ = "pantry_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    canonical_food_id: Mapped[str] = mapped_column(ForeignKey("canonical_foods.id"), index=True)
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20))
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    location: Mapped[str] = mapped_column(String(80), default="厨房")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)


class PrivateKnowledge(Base):
    __tablename__ = "private_knowledge"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(50))
    tags: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MealPlanRecord(Base):
    __tablename__ = "meal_plans"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    query: Mapped[str] = mapped_column(Text)
    plan_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="proposed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DietRecord(Base):
    __tablename__ = "diet_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    meal_plan_id: Mapped[str] = mapped_column(ForeignKey("meal_plans.id"))
    consumption_json: Mapped[str] = mapped_column(Text)
    estimated_nutrition_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    meal_plan_id: Mapped[str] = mapped_column(ForeignKey("meal_plans.id"))
    transaction_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class InventoryTransactionLine(Base):
    __tablename__ = "inventory_transaction_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("inventory_transactions.id"), index=True)
    pantry_item_id: Mapped[int] = mapped_column(ForeignKey("pantry_items.id"))
    quantity_before: Mapped[float] = mapped_column(Float)
    quantity_change: Mapped[float] = mapped_column(Float)
    quantity_after: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80))
    node_name: Mapped[str] = mapped_column(String(80))
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PromptExperiment(Base):
    __tablename__ = "prompt_experiments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    variant: Mapped[str] = mapped_column(String(20))
    test_case: Mapped[str] = mapped_column(String(100))
    output_json: Mapped[str] = mapped_column(Text)
    validation_passed: Mapped[bool] = mapped_column(Boolean)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
