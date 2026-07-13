from pydantic import BaseModel, Field


class ConsumptionItem(BaseModel):
    canonical_item_id: str
    amount: float = Field(gt=0)
    unit: str

