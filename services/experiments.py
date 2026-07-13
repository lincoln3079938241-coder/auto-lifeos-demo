from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from database.models import PromptExperiment
from database.repositories import get_profile, list_inventory, list_knowledge
from database.seed import DEMO_USER_ID
from database.session import get_session
from agent.nodes.guardrails import eligible_inventory, validate_plan
from llm.mock_provider import MockProvider
from rag.retriever import retrieve

PROMPTS = {
    "A": "根据用户请求生成饮食推荐。",
    "B": "仅使用提供库存候选；返回严格 MealPlan JSON，包含食材 ID 与检索证据；遵循过敏和忌口；不确定时说明需要澄清。",
}

PUBLIC_ROOT = Path(__file__).resolve().parents[1]


def run_synthetic_experiment(cases_path: str | Path | None = None) -> list[dict[str, Any]]:
    resolved_path = Path(cases_path) if cases_path else PUBLIC_ROOT / "data" / "synthetic_ab_cases.json"
    cases = json.loads(resolved_path.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    with get_session() as session:
        profile = get_profile(session, DEMO_USER_ID)
        inventory = list_inventory(session, DEMO_USER_ID)
        knowledge = list_knowledge(session, DEMO_USER_ID)
        allowed, _ = eligible_inventory(profile, inventory)
        for variant, prompt in PROMPTS.items():
            for case in cases:
                started = time.perf_counter()
                try:
                    evidence = retrieve(case["query"], knowledge)
                    requirements = {"query": case["query"], "max_minutes": 30,
                                    "vegetarian": "素" in case["query"], "high_protein": "蛋白" in case["query"]}
                    plan = MockProvider().generate(requirements, allowed, evidence, profile)
                    errors = validate_plan(plan, profile, inventory)
                    output = {"plan": plan.model_dump(), "errors": errors, "prompt": prompt}
                    parsed = True
                except Exception as exc:
                    output, errors, parsed = {"error": str(exc), "prompt": prompt}, [str(exc)], False
                latency = round((time.perf_counter() - started) * 1000, 2)
                row = {"variant": variant, "test_case": case["id"], "category": case["category"], "parsed": parsed,
                       "validation_passed": not errors, "retry_count": 0, "latency_ms": latency,
                       "hallucinated_food_count": 0 if parsed and not errors else 1, "needs_clarification": "ambiguous" in case["category"],
                       "executable": parsed and not errors, "output": output}
                results.append(row)
                session.add(PromptExperiment(variant=variant, test_case=case["id"], output_json=json.dumps(output, ensure_ascii=False),
                             validation_passed=not errors, retry_count=0, latency_ms=latency))
        session.commit()
    return results


def summarize_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    for variant in PROMPTS:
        rows = [row for row in results if row["variant"] == variant]
        n = max(len(rows), 1)
        summary.append({"variant": variant, "cases": len(rows),
                        "pydantic_parse_rate": round(sum(r["parsed"] for r in rows) / n, 3),
                        "validation_pass_rate": round(sum(r["validation_passed"] for r in rows) / n, 3),
                        "hallucinated_food_count": sum(r["hallucinated_food_count"] for r in rows),
                        "avg_retry_count": round(sum(r["retry_count"] for r in rows) / n, 2),
                        "avg_latency_ms": round(sum(r["latency_ms"] for r in rows) / n, 2),
                        "needs_clarification_count": sum(r["needs_clarification"] for r in rows),
                        "executable_rate": round(sum(r["executable"] for r in rows) / n, 3)})
    return summary
