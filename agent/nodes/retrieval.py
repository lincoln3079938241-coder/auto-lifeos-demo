from __future__ import annotations

from database.repositories import list_knowledge
from database.session import get_session
from rag.retriever import retrieve
from agent.nodes.shared import update_with_audit


def retrieve_private_knowledge(state: dict) -> dict:
    with get_session() as session:
        rows = list_knowledge(session, state["user_id"])
    context = retrieve(state["raw_query"], rows)
    return update_with_audit(state, "retrieve_private_knowledge", f"检索到 {len(context)} 条私域知识", retrieved_context=context)

