from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from schemas.meal_plan import MealPlan


class MealPlanProvider(ABC):
    name = "base"

    @abstractmethod
    def generate(self, requirements: dict[str, Any], inventory: list[dict[str, Any]],
                 evidence: list[dict[str, Any]], profile: dict[str, Any]) -> MealPlan:
        raise NotImplementedError


def get_provider() -> tuple[MealPlanProvider, str]:
    """Return the only provider available in the public demo."""
    from llm.mock_provider import MockProvider

    return MockProvider(), "Mock Provider · deterministic sample generator · no API key"
