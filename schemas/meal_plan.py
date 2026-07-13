from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IngredientUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canonical_item_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    amount: float = Field(gt=0)
    unit: str = Field(min_length=1)
    available_amount: float = Field(ge=0)
    inventory_unit: str = Field(min_length=1)
    source: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)

    @field_validator("unit", "inventory_unit")
    @classmethod
    def known_units(cls, value: str) -> str:
        if value.lower() not in {"g", "kg", "ml", "l", "个", "piece"}:
            raise ValueError(f"无法识别的单位: {value}")
        return value.lower()


class MealPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: str = Field(min_length=4)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    estimated_minutes: int = Field(gt=0, le=180)
    calories_kcal: float = Field(gt=0, le=3000)
    protein_g: float = Field(ge=0, le=400)
    carbs_g: float = Field(ge=0, le=600)
    fat_g: float = Field(ge=0, le=300)
    ingredients: list[IngredientUsage] = Field(min_length=1)
    steps: list[str] = Field(min_length=1)
    reasons: list[str] = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)
    retrieved_evidence_ids: list[int] = Field(default_factory=list)

