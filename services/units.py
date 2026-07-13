from __future__ import annotations

UNIT_FACTORS = {"g": ("mass", 1.0), "kg": ("mass", 1000.0), "ml": ("volume", 1.0), "l": ("volume", 1000.0), "个": ("count", 1.0), "piece": ("count", 1.0)}


def is_known_unit(unit: str) -> bool:
    return unit.lower() in UNIT_FACTORS


def convert_amount(amount: float, source_unit: str, target_unit: str) -> float:
    source, target = source_unit.lower(), target_unit.lower()
    if source not in UNIT_FACTORS or target not in UNIT_FACTORS:
        raise ValueError("无法识别的单位")
    source_kind, source_factor = UNIT_FACTORS[source]
    target_kind, target_factor = UNIT_FACTORS[target]
    if source_kind != target_kind:
        raise ValueError(f"单位不可换算: {source_unit} -> {target_unit}")
    return amount * source_factor / target_factor

