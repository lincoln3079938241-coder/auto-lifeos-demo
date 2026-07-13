from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.state import AgentState
from agent.routes import route_execution, route_first_confirmation, route_intent, route_second_confirmation, route_validation
from agent.nodes.confirmation import collect_actual_consumption, wait_first_confirmation, wait_second_confirmation
from agent.nodes.execution import execute_inventory_transaction, write_audit_log, write_diet_record
from agent.nodes.fallback import fallback_handler, final_response, inventory_query_response
from agent.nodes.generation import generate_plan
from agent.nodes.guardrails import deterministic_guard
from agent.nodes.intent import intent_router
from agent.nodes.inventory import load_inventory
from agent.nodes.normalization import normalize_entities
from agent.nodes.profile import load_user_profile
from agent.nodes.retrieval import retrieve_private_knowledge
from agent.nodes.validation import plan_revision, validate_generated_plan


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("intent_router", intent_router)
    graph.add_node("load_user_profile", load_user_profile)
    graph.add_node("retrieve_private_knowledge", retrieve_private_knowledge)
    graph.add_node("load_inventory", load_inventory)
    graph.add_node("normalize_entities", normalize_entities)
    graph.add_node("deterministic_guard", deterministic_guard)
    graph.add_node("generate_plan", generate_plan)
    graph.add_node("validate_plan", validate_generated_plan)
    graph.add_node("plan_revision", plan_revision)
    graph.add_node("wait_first_confirmation", wait_first_confirmation)
    graph.add_node("collect_actual_consumption", collect_actual_consumption)
    graph.add_node("wait_second_confirmation", wait_second_confirmation)
    graph.add_node("execute_inventory_transaction", execute_inventory_transaction)
    graph.add_node("write_diet_record", write_diet_record)
    graph.add_node("write_audit_log", write_audit_log)
    graph.add_node("fallback_handler", fallback_handler)
    graph.add_node("inventory_query_response", inventory_query_response)
    graph.add_node("final_response", final_response)
    graph.add_edge(START, "intent_router")
    graph.add_conditional_edges("intent_router", route_intent, {"meal": "load_user_profile", "inventory": "load_inventory", "fallback": "fallback_handler"})
    graph.add_edge("load_user_profile", "retrieve_private_knowledge")
    graph.add_edge("retrieve_private_knowledge", "load_inventory")
    # The inventory-query branch reads authoritative structured inventory but does not enter meal generation.
    graph.add_conditional_edges("load_inventory", lambda state: "summary" if state.get("intent") == "inventory_query" else "meal", {"summary": "inventory_query_response", "meal": "normalize_entities"})
    graph.add_edge("normalize_entities", "deterministic_guard")
    graph.add_edge("deterministic_guard", "generate_plan")
    graph.add_edge("generate_plan", "validate_plan")
    graph.add_conditional_edges("validate_plan", route_validation, {"confirmed_plan": "wait_first_confirmation", "revise": "plan_revision", "fallback": "fallback_handler"})
    graph.add_edge("plan_revision", "generate_plan")
    graph.add_conditional_edges("wait_first_confirmation", route_first_confirmation, {"accepted": "collect_actual_consumption", "rejected": "fallback_handler", "wait": "final_response"})
    graph.add_edge("collect_actual_consumption", "wait_second_confirmation")
    graph.add_conditional_edges("wait_second_confirmation", route_second_confirmation, {"accepted": "execute_inventory_transaction", "rejected": "fallback_handler", "wait": "final_response"})
    graph.add_conditional_edges("execute_inventory_transaction", route_execution, {"written": "write_diet_record", "fallback": "fallback_handler"})
    graph.add_edge("write_diet_record", "write_audit_log")
    graph.add_edge("write_audit_log", "final_response")
    graph.add_edge("fallback_handler", "final_response")
    graph.add_edge("inventory_query_response", "final_response")
    graph.add_edge("final_response", END)
    return graph.compile()


agent_graph = build_graph()


def run_agent(state: AgentState) -> AgentState:
    return agent_graph.invoke(state)  # type: ignore[return-value]
