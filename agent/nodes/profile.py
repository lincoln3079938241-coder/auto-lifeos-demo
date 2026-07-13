from __future__ import annotations

from database.repositories import get_profile
from database.session import get_session
from agent.nodes.shared import update_with_audit


def load_user_profile(state: dict) -> dict:
    with get_session() as session:
        profile = get_profile(session, state["user_id"])
    if not profile:
        return update_with_audit(state, "load_user_profile", "用户档案不存在", error="用户档案不存在")
    return update_with_audit(state, "load_user_profile", "已读取用户目标、过敏与偏好", user_profile=profile)

