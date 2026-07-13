from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st


PUBLIC_ROOT = Path(__file__).resolve().parent
if str(PUBLIC_ROOT) not in sys.path:
    sys.path.insert(0, str(PUBLIC_ROOT))

from agent.graph import run_agent
from agent.state import initial_state
from database.repositories import (
    latest_executable_transaction,
    list_inventory,
    list_inventory_transaction_lines,
    list_knowledge,
)
from database.seed import DEMO_USER_ID
from database.session import get_session
from database.transactions import undo_transaction
from rag.retriever import retrieve
from services.experiments import PROMPTS, run_synthetic_experiment, summarize_results
from services.units import convert_amount
from session_store import SessionWorkspace


LOGGER = logging.getLogger("auto_lifeos.public_demo")

st.set_page_config(
    page_title="今天吃什么？· Auto-LifeOS",
    page_icon="🥗",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      .block-container {max-width: 980px; padding-top: 1.4rem; padding-bottom: 3rem;}
      [data-testid="stMetric"] {background:#fff; border:1px solid #e2ebe5; border-radius:14px; padding:.9rem;}
      [data-testid="stDataFrame"] {border:1px solid #e2ebe5; border-radius:12px; overflow:hidden;}
      [data-testid="stButton"] button {min-height:44px; border-radius:10px;}
      .hero {padding:.4rem 0 .2rem;}
      .hero h1 {font-size:clamp(2rem,5vw,3.15rem); line-height:1.15; margin:.2rem 0 .75rem; color:#173d27;}
      .hero p {font-size:1.08rem; line-height:1.75; color:#5e6e64; max-width:760px; margin:0;}
      .badge-row {display:flex; flex-wrap:wrap; gap:8px; margin:1rem 0 1.35rem;}
      .badge {display:inline-flex; align-items:center; padding:5px 11px; border-radius:999px;
        background:#edf7f0; border:1px solid #d4e8da; color:#2d6340; font-size:.82rem; font-weight:650;}
      .progress-grid {display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin:1rem 0 1.4rem;}
      .progress-item {border:1px solid #e2e9e4; border-radius:12px; padding:10px 12px; background:#fafcfb;}
      .progress-item .number {font-size:.72rem; letter-spacing:.08em; color:#87928b;}
      .progress-item .label {font-size:.92rem; color:#6b776f; margin-top:3px;}
      .progress-item.done {background:#f0f8f2; border-color:#cfe6d5;}
      .progress-item.done .label {color:#28663c; font-weight:700;}
      .progress-item.current {background:#fff8eb; border-color:#efd39d; box-shadow:0 0 0 2px rgba(216,160,55,.08);}
      .progress-item.current .label {color:#8a5800; font-weight:750;}
      .compact-note {background:#f6f9f7; border-left:3px solid #8dbb9a; padding:10px 12px;
        border-radius:0 10px 10px 0; color:#53645a; font-size:.9rem; margin:.7rem 0 1rem;}
      .food-title {font-size:1.02rem; font-weight:750; color:#263c2e; margin-bottom:.3rem;}
      .food-meta {color:#66746b; font-size:.9rem; line-height:1.65;}
      .section-kicker {font-size:.78rem; font-weight:750; letter-spacing:.08em; color:#4f8a63; margin-bottom:.35rem;}
      .footer-note {color:#7c8881; font-size:.78rem; text-align:center; margin-top:1.5rem;}
      @media (max-width: 640px) {
        .block-container {padding:1rem 1rem 2.5rem;}
        .hero h1 {font-size:2rem;}
        .hero p {font-size:.98rem; line-height:1.65;}
        .progress-grid {grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px;}
        .progress-item {padding:9px 10px;}
        [data-testid="stHorizontalBlock"] {gap:.65rem;}
      }
    </style>
    """,
    unsafe_allow_html=True,
)


SAMPLE_QUERIES = {
    "高蛋白低脂晚餐": "今晚想吃高蛋白、低脂、30分钟以内可以完成的食物。",
    "简单营养早餐": "请推荐一份简单、有蛋白质、20分钟以内可以完成的早餐。",
    "使用现有食材": "请根据家里现有的演示食材，推荐一份容易完成的饭菜。",
}

NODE_LABELS = {
    "intent_router": "理解你的需求",
    "load_user_profile": "查看演示饮食习惯",
    "retrieve_private_knowledge": "查找相关偏好",
    "load_inventory": "查看现有演示食材",
    "normalize_entities": "整理时间和食材要求",
    "deterministic_guard": "排除不能使用的食材",
    "generate_plan": "生成推荐方案",
    "validate_plan": "检查方案是否可用",
    "plan_revision": "重新寻找合适方案",
    "wait_first_confirmation": "等待你确认方案",
    "collect_actual_consumption": "记录实际使用量",
    "wait_second_confirmation": "等待你确认实际用量",
    "execute_inventory_transaction": "更新演示库存",
    "write_diet_record": "保存本次使用记录",
    "write_audit_log": "保存执行过程",
    "fallback_handler": "换用备用推荐方式",
    "inventory_query_response": "整理演示库存",
    "final_response": "完成本次操作",
}


def workspace() -> SessionWorkspace:
    if "_workspace" not in st.session_state:
        st.session_state._workspace = SessionWorkspace()
    current: SessionWorkspace = st.session_state._workspace
    current.activate()
    return current


CURRENT_WORKSPACE = workspace()
st.session_state.setdefault("meal_query", "")
st.session_state.setdefault("agent_state", None)
st.session_state.setdefault("completion_undone", False)


def reset_current_session() -> None:
    CURRENT_WORKSPACE.reset()
    for key in list(st.session_state.keys()):
        if key != "_workspace":
            del st.session_state[key]


def clear_flow(clear_query: bool = False) -> None:
    st.session_state.agent_state = None
    st.session_state.completion_undone = False
    if clear_query:
        st.session_state.meal_query = ""
    for key in list(st.session_state.keys()):
        if key.startswith("actual_use_"):
            del st.session_state[key]


def compact_boundaries() -> None:
    st.markdown(
        '<div class="badge-row"><span class="badge">无需登录</span>'
        '<span class="badge">使用虚拟演示数据</span><span class="badge">不构成医疗建议</span></div>',
        unsafe_allow_html=True,
    )


def secondary_header(title: str, subtitle: str) -> None:
    st.title(title)
    st.caption(subtitle)
    compact_boundaries()


def help_panel() -> None:
    with st.expander("第一次使用？点击查看说明"):
        st.markdown(
            "1. 输入想吃什么。\n"
            "2. 点击“帮我推荐”。\n"
            "3. 查看并确认方案。\n"
            "4. 修改并确认实际使用量。\n"
            "5. 查看库存变化，需要时可以撤销。"
        )
        st.caption(
            "第一次打开可能需要等待一会儿；无需注册和 API Key；所有数据均为虚拟演示数据；"
            "数据可能在页面关闭或服务重启后恢复；内容不构成医疗诊断或治疗建议。"
        )


def flow_stage(state: dict | None) -> int:
    if not state or not state.get("proposed_plan"):
        return 1
    if state.get("first_confirmation") is not True:
        return 2
    if not state.get("transaction_id"):
        return 3
    return 4


def flow_steps(state: dict | None) -> None:
    current = flow_stage(state)
    steps = ["说出需求", "查看推荐", "确认用量", "更新库存"]
    cards = []
    for index, label in enumerate(steps, 1):
        css = "done" if index < current or (current == 4 and index == 4) else "current" if index == current else ""
        status = "已完成" if css == "done" else "当前" if css == "current" else "待进行"
        cards.append(
            f'<div class="progress-item {css}"><div class="number">{index:02d} · {status}</div>'
            f'<div class="label">{label}</div></div>'
        )
    st.markdown('<div class="progress-grid">' + "".join(cards) + "</div>", unsafe_allow_html=True)


def run_current_agent(**updates: object) -> None:
    state = st.session_state.get("agent_state")
    if not state:
        return
    state.update(updates)
    st.session_state.agent_state = run_agent(state)


def inventory_change_rows(state: dict, usages: list[dict] | None = None) -> list[dict]:
    plan = state.get("proposed_plan") or {}
    by_id = {item["canonical_item_id"]: item for item in plan.get("ingredients", [])}
    rows: list[dict] = []
    for usage in usages or state.get("actual_consumption") or []:
        ingredient = by_id.get(usage["canonical_item_id"])
        if not ingredient:
            continue
        before = float(ingredient["available_amount"])
        unit = ingredient["inventory_unit"]
        used = convert_amount(float(usage["amount"]), usage["unit"], unit)
        rows.append(
            {
                "食材": ingredient["display_name"],
                "更新前数量": round(before, 2),
                "本次使用": round(used, 2),
                "更新后数量": round(before - used, 2),
                "单位": unit,
            }
        )
    return rows


def recommendation_card(state: dict) -> None:
    plan = state["proposed_plan"]
    with st.container(border=True):
        st.markdown('<div class="section-kicker">为你找到一份容易执行的方案</div>', unsafe_allow_html=True)
        st.header(plan["title"])
        st.write(plan["description"])
        metrics = st.columns(3)
        metrics[0].metric("预计完成时间", f"{plan['estimated_minutes']} 分钟")
        metrics[1].metric("预计热量", f"{plan['calories_kcal']} kcal")
        metrics[2].metric("蛋白质", f"{plan['protein_g']} g")

        st.markdown("#### 需要准备")
        ingredient_rows = [
            {"食材": item["display_name"], "需要数量": item["amount"], "单位": item["unit"]}
            for item in plan["ingredients"]
        ]
        st.dataframe(pd.DataFrame(ingredient_rows), use_container_width=True, hide_index=True)

        left, right = st.columns(2)
        with left:
            st.markdown("#### 为什么推荐")
            for reason in plan["reasons"]:
                st.markdown(f"- {reason}")
        with right:
            st.markdown("#### 简单做法")
            for index, step in enumerate(plan["steps"], 1):
                st.markdown(f"{index}. {step}")
        if plan.get("warnings"):
            st.markdown("#### 注意事项")
            st.info("；".join(plan["warnings"]))

    with st.expander("查看详细技术信息"):
        st.write("生成方式：Mock Provider（本地规则模拟，不需要 API Key）")
        st.write("结构化计划已经过库存、过敏原、过期食材、单位和营养范围检查。")
        st.caption(f"Plan ID：{plan['plan_id']}")
        evidence = {row["id"]: row for row in state.get("retrieved_context", [])}
        selected = [evidence[item_id] for item_id in plan.get("retrieved_evidence_ids", []) if item_id in evidence]
        if selected:
            st.dataframe(
                pd.DataFrame(selected)[["title", "source_type", "score"]].rename(
                    columns={"title": "推荐参考信息", "source_type": "来源类型", "score": "相关度"}
                ),
                use_container_width=True,
                hide_index=True,
            )


def actual_usage_editor(state: dict) -> list[dict]:
    plan = state["proposed_plan"]
    existing = {item["canonical_item_id"]: item for item in state.get("actual_consumption", [])}
    usages: list[dict] = []
    preview_rows: list[dict] = []
    for ingredient in plan["ingredients"]:
        food_id = ingredient["canonical_item_id"]
        unit = ingredient["unit"]
        default_amount = float(existing.get(food_id, {}).get("amount", ingredient["amount"]))
        key = f"actual_use_{plan['plan_id']}_{food_id}"
        with st.container(border=True):
            st.markdown(f'<div class="food-title">{ingredient["display_name"]}</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="food-meta">原有库存：{ingredient["available_amount"]} {ingredient["inventory_unit"]}<br>'
                f'计划使用：{ingredient["amount"]} {unit}</div>',
                unsafe_allow_html=True,
            )
            amount = st.number_input(
                f"实际使用（{unit}）",
                min_value=0.01,
                max_value=float(ingredient["available_amount"]),
                value=default_amount,
                step=1.0,
                key=key,
            )
            remaining = float(ingredient["available_amount"]) - convert_amount(
                float(amount), unit, ingredient["inventory_unit"]
            )
            st.caption(f"使用后剩余：{round(remaining, 2)} {ingredient['inventory_unit']}")
        usages.append({"canonical_item_id": food_id, "amount": float(amount), "unit": unit})
        preview_rows.append(
            {
                "食材": ingredient["display_name"],
                "原有库存": ingredient["available_amount"],
                "计划使用": ingredient["amount"],
                "实际使用": float(amount),
                "使用后剩余": round(remaining, 2),
                "单位": ingredient["inventory_unit"],
            }
        )
    st.markdown("#### 确认后的变化")
    st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)
    return usages


def undo_latest_update() -> bool:
    with get_session() as session:
        transaction = latest_executable_transaction(session, DEMO_USER_ID)
        if transaction is None:
            return False
        undo_transaction(session, transaction.id, CURRENT_WORKSPACE.session_id)
    st.session_state.completion_undone = True
    return True


def reset_controls(key_prefix: str) -> None:
    st.divider()
    with st.expander("演示设置"):
        st.caption("如果页面状态混乱，可以只恢复当前浏览会话的虚拟演示数据，不会影响其他访问者。")
        if st.button("恢复当前演示数据", key=f"{key_prefix}_reset", use_container_width=True):
            reset_current_session()
            st.rerun()


def start_page() -> None:
    st.markdown(
        '<div class="hero"><h1>今天吃什么？让智能助手帮你想一想</h1>'
        '<p>告诉我你想吃什么、有什么要求，我会结合当前的演示食材，为你推荐一份简单的饮食方案。</p></div>',
        unsafe_allow_html=True,
    )
    compact_boundaries()
    help_panel()

    state = st.session_state.get("agent_state")
    flow_steps(state)

    if not state:
        if notice := st.session_state.pop("flow_notice", None):
            st.info(notice)
        st.markdown("### 你今天想吃什么？")
        st.caption("可以告诉我时间、口味或饮食要求，例如“高蛋白、少油、30分钟以内”。")
        example_columns = st.columns(3)
        for column, (label, query) in zip(example_columns, SAMPLE_QUERIES.items()):
            if column.button(label, key=f"example_{label}", use_container_width=True):
                st.session_state.meal_query = query
                st.rerun()
        query = st.text_area(
            "你的想法",
            key="meal_query",
            placeholder="例如：今晚想吃高蛋白、低脂、30分钟以内可以完成的食物。",
            height=110,
            label_visibility="collapsed",
        )
        if st.button("帮我推荐", type="primary", disabled=not query.strip(), use_container_width=True):
            try:
                with st.spinner("正在查看饮食习惯和现有食材，请稍等……"):
                    st.session_state.agent_state = run_agent(
                        initial_state(CURRENT_WORKSPACE.session_id, DEMO_USER_ID, query.strip())
                    )
                st.session_state.completion_undone = False
                st.rerun()
            except Exception:
                LOGGER.exception("Recommendation generation failed")
                st.error("暂时没有找到合适的方案，请换一种说法再试。")

    elif state.get("error") and not state.get("proposed_plan"):
        st.error("暂时没有找到合适的方案。可以换一种说法，或检查当前演示库存后再试。")
        if st.button("重新输入", type="primary", use_container_width=True):
            clear_flow()
            st.rerun()

    elif state.get("proposed_plan") and state.get("first_confirmation") is not True:
        recommendation_card(state)
        st.markdown('<div class="compact-note">确认方案不会立即修改库存，下一步还会让你确认实际使用量。</div>', unsafe_allow_html=True)
        confirm, replace = st.columns(2)
        if confirm.button("这个方案可以", type="primary", use_container_width=True):
            try:
                run_current_agent(first_confirmation=True)
                st.rerun()
            except Exception:
                LOGGER.exception("First confirmation failed")
                st.error("页面暂时出现问题，请恢复当前演示数据后重试。")
        if replace.button("换一个方案", use_container_width=True):
            clear_flow()
            st.session_state.flow_notice = "可以修改刚才的要求，或者选择另一个示例。演示库存没有变化。"
            st.rerun()

    elif state.get("first_confirmation") is True and not state.get("transaction_id"):
        st.header("实际用了多少食材？")
        st.write("你可以按照实际情况修改数量。只有下一步再次确认后，演示库存才会更新。")
        usages = actual_usage_editor(state)
        st.markdown(
            '<div class="compact-note"><b>这是第二次确认。</b>点击后才会更新当前会话的演示库存。</div>',
            unsafe_allow_html=True,
        )
        update, back = st.columns(2)
        if update.button("确认并更新演示库存", type="primary", use_container_width=True):
            try:
                run_current_agent(actual_consumption=usages, second_confirmation=True)
                st.rerun()
            except Exception:
                LOGGER.exception("Inventory update failed")
                st.error("演示库存暂时无法更新，请检查实际使用量后重试。")
        if back.button("返回修改方案", use_container_width=True):
            clear_flow()
            st.session_state.flow_notice = "已返回需求输入，演示库存没有变化。"
            st.rerun()

    else:
        if st.session_state.get("completion_undone"):
            st.success("已撤销，本次使用的食材已经恢复。")
            st.dataframe(pd.DataFrame(inventory_change_rows(state)), use_container_width=True, hide_index=True)
            if st.button("再推荐一份", type="primary", use_container_width=True):
                clear_flow(clear_query=True)
                st.rerun()
        else:
            st.success("已完成，本次演示库存已更新")
            st.markdown("### 本次食材变化")
            st.dataframe(pd.DataFrame(inventory_change_rows(state)), use_container_width=True, hide_index=True)
            undo, restart = st.columns(2)
            if undo.button("撤销本次更新", type="primary", use_container_width=True):
                try:
                    if undo_latest_update():
                        st.rerun()
                    else:
                        st.info("本次更新已经撤销，无需重复操作。")
                except Exception:
                    LOGGER.exception("Undo failed")
                    st.error("暂时无法撤销，请稍后重试。")
            if restart.button("再推荐一份", use_container_width=True):
                clear_flow(clear_query=True)
                st.rerun()

    reset_controls("start")


def inventory_page() -> None:
    secondary_header("演示库存", "这里展示当前浏览会话可以使用的虚拟食材。")
    with get_session() as session:
        inventory = list_inventory(session, DEMO_USER_ID)

    expired_count = sum(item["expired"] for item in inventory)
    near_expiry = sum(
        bool(item["expiration_date"] and 0 <= (item["expiration_date"] - date.today()).days <= 3)
        for item in inventory
    )
    metrics = st.columns(3)
    metrics[0].metric("可以使用", len(inventory) - expired_count)
    metrics[1].metric("即将到期", near_expiry)
    metrics[2].metric("不能使用", expired_count)

    frame = pd.DataFrame(inventory)
    if not frame.empty:
        frame["状态"] = frame.apply(
            lambda row: "已过期"
            if row["expired"]
            else "即将到期"
            if row["expiration_date"] and 0 <= (row["expiration_date"] - date.today()).days <= 3
            else "可以使用",
            axis=1,
        )
        frame = frame.rename(
            columns={
                "canonical_name": "食材",
                "quantity": "当前数量",
                "unit": "单位",
                "expiration_date": "到期日",
                "location": "存放位置",
            }
        )
        st.dataframe(
            frame[["食材", "当前数量", "单位", "到期日", "存放位置", "状态"]],
            use_container_width=True,
            hide_index=True,
        )
    st.caption("食材数量只属于当前浏览会话，其他访问者看不到也不会受到影响。")
    reset_controls("inventory")


def records_page() -> None:
    secondary_header("使用记录", "查看当前浏览会话更新过哪些演示食材，并在需要时撤销最近一次更新。")
    with get_session() as session:
        transactions = list_inventory_transaction_lines(session, DEMO_USER_ID)
        latest = latest_executable_transaction(session, DEMO_USER_ID)

    if not transactions:
        st.info("完成一次饮食推荐并更新演示库存后，这里会显示食材变化。")
    else:
        frame = pd.DataFrame(transactions).rename(
            columns={
                "status": "状态",
                "created_at": "更新时间",
                "canonical_name": "食材",
                "quantity_before": "更新前",
                "quantity_change": "变化量",
                "quantity_after": "更新后",
                "unit": "单位",
            }
        )
        frame["状态"] = frame["状态"].map({"completed": "已更新", "reversed": "已撤销"}).fillna(frame["状态"])
        st.dataframe(
            frame[["更新时间", "食材", "更新前", "变化量", "更新后", "单位", "状态"]],
            use_container_width=True,
            hide_index=True,
        )
        if latest and st.button("撤销最近一次更新", type="primary", use_container_width=True):
            try:
                with get_session() as session:
                    undo_transaction(session, latest.id, CURRENT_WORKSPACE.session_id)
                st.session_state.completion_undone = True
                st.success("已撤销，本次使用的食材已经恢复。")
                st.rerun()
            except Exception:
                LOGGER.exception("Record-page undo failed")
                st.error("暂时无法撤销，请稍后重试。")
    reset_controls("records")


def project_page() -> None:
    secondary_header("了解项目原理", "以下内容面向希望了解技术实现、工程验证和安全边界的访问者。")

    with st.expander("这个项目解决什么问题", expanded=True):
        st.write(
            "很多饮食推荐只给出文字建议，却不知道家里有什么食材，也不会在执行前再次确认。"
            "这个演示把需求理解、饮食习惯、现有食材和两次确认连成一个可撤销的流程。"
        )

    with st.expander("系统是怎样得出推荐的"):
        st.markdown(
            "**普通用户看到的流程**\n\n"
            "说出需求 → 查看饮食习惯和食材 → 生成方案 → 检查是否可执行 → 两次确认 → 更新演示库存\n\n"
            "**技术实现**\n\n"
            "LangGraph 负责流程编排；Pydantic 约束结构化计划；Python guardrails 检查过期食材、过敏原、单位和库存；"
            "SQLite 事务负责更新与撤销。"
        )

    with st.expander("我的饮食习惯（知识检索）"):
        with get_session() as session:
            rows = list_knowledge(session, DEMO_USER_ID)
        st.dataframe(
            pd.DataFrame(rows)[["title", "content", "source_type"]].rename(
                columns={"title": "内容主题", "content": "虚拟演示内容", "source_type": "信息类型"}
            ),
            use_container_width=True,
            hide_index=True,
        )
        query = st.text_input("查找相关饮食习惯", placeholder="例如：鸡胸肉和番茄", key="principle_knowledge_query")
        if query:
            results = retrieve(query, rows)
            if results:
                st.dataframe(
                    pd.DataFrame(results)[["title", "content", "score"]].rename(
                        columns={"title": "推荐参考信息", "content": "内容", "score": "相关度"}
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("当前虚拟饮食习惯中没有找到足够相关的内容。")

    with st.expander("系统是怎样得出结果的（Agent Trace）"):
        state = st.session_state.get("agent_state")
        if not state:
            st.info("完成一次推荐后，这里会用普通中文展示系统做过哪些步骤。")
        else:
            events = state.get("audit_events", [])
            trace = pd.DataFrame(
                [
                    {
                        "步骤": index,
                        "做了什么": NODE_LABELS.get(event.get("node_name"), event.get("node_name")),
                        "结果说明": event.get("summary"),
                        "技术名称": event.get("node_name"),
                    }
                    for index, event in enumerate(events, 1)
                ]
            )
            st.dataframe(trace, use_container_width=True, hide_index=True)
            metrics = st.columns(3)
            metrics[0].metric("执行步骤", len(events))
            metrics[1].metric("重新寻找方案", state.get("retry_count", 0))
            metrics[2].metric("未通过检查", len(state.get("validation_errors", [])))

    with st.expander("两种推荐方式对比（Prompt A/B）"):
        st.caption("这是 synthetic/sample 规则模拟，不是真实用户实验，不代表满意度、留存、转化率或业务收益。")
        if st.button("运行两种推荐方式对比", type="primary", key="run_experiment"):
            with st.spinner("正在运行 40 次虚拟案例检查……"):
                st.session_state.ab_results = run_synthetic_experiment()
        if results := st.session_state.get("ab_results"):
            summary = pd.DataFrame(summarize_results(results)).rename(
                columns={
                    "variant": "方式",
                    "cases": "虚拟案例数",
                    "pydantic_parse_rate": "结构读取成功率",
                    "validation_pass_rate": "规则检查通过率",
                    "hallucinated_food_count": "不存在的食材数",
                    "avg_retry_count": "平均重新推荐次数",
                    "avg_latency_ms": "平均耗时(ms)",
                    "needs_clarification_count": "需要补充说明",
                    "executable_rate": "可执行率",
                }
            )
            st.dataframe(summary, use_container_width=True, hide_index=True)
        else:
            st.caption("点击上方按钮后显示两种方式在虚拟案例中的检查结果。")
        st.markdown("**Prompt 原文**")
        st.code(f"方式 A：{PROMPTS['A']}\n\n方式 B：{PROMPTS['B']}")

    with st.expander("工程测试"):
        checks = pd.DataFrame(
            [
                {"检查范围": "主项目自动化测试", "最近验证": "27 passed"},
                {"检查范围": "公开版自动化测试", "最近验证": "会话隔离、两次确认、撤销与页面主流程"},
                {"检查范围": "公开网站", "最近验证": "桌面、手机尺寸与 HTTP 200"},
            ]
        )
        st.dataframe(checks, use_container_width=True, hide_index=True)

    with st.expander("安全与限制"):
        st.markdown(
            "- 所有用户、食材、饮食习惯和实验数据均为 synthetic/sample。\n"
            "- 每个浏览会话使用独立的临时 SQLite 数据库。\n"
            "- 公开版只使用 Mock Provider，不连接外部模型，也不读取 API Key。\n"
            "- 推荐只是一般饮食演示，不构成医疗诊断或治疗建议。\n"
            "- 页面关闭、会话断开或服务重启后，临时数据可能恢复到初始状态。"
        )
    reset_controls("project")


PAGES = {
    "开始体验": start_page,
    "演示库存": inventory_page,
    "使用记录": records_page,
    "了解项目原理": project_page,
}

with st.sidebar:
    st.title("Auto-LifeOS")
    st.caption("饮食推荐公开演示")
    selected_page = st.radio("页面导航", list(PAGES), label_visibility="collapsed")
    st.divider()
    st.caption("无需登录 · 虚拟演示数据 · 不构成医疗建议")

try:
    PAGES[selected_page]()
except Exception:
    LOGGER.exception("Unhandled public demo error")
    st.error("页面暂时出现问题，请点击“恢复当前演示数据”后重试。")
    if st.button("恢复当前演示数据", key="error_reset", use_container_width=True):
        reset_current_session()
        st.rerun()

st.markdown('<div class="footer-note">Auto-LifeOS 公开演示 · 所有数据均为虚拟样例</div>', unsafe_allow_html=True)
