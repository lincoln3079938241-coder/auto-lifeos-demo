from __future__ import annotations

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


st.set_page_config(page_title="Auto-LifeOS · Public Demo", page_icon="🥗", layout="wide")

st.markdown(
    """
    <style>
      .block-container {max-width: 1180px; padding-top: 1.6rem; padding-bottom: 3rem;}
      [data-testid="stMetric"] {background:#fff; border:1px solid #e3ebe6; border-radius:14px; padding:1rem;}
      [data-testid="stDataFrame"] {border:1px solid #e3ebe6; border-radius:12px; overflow:hidden;}
      .demo-pill {display:inline-block; padding:4px 10px; border-radius:99px; background:#dff3e5;
        color:#205b34; font-size:.76rem; font-weight:750; letter-spacing:.04em;}
      .notice {background:linear-gradient(90deg,#eff9f2,#f8fbf9); border:1px solid #cce5d3;
        border-radius:13px; padding:12px 15px; color:#315b3d; margin:.65rem 0 1.25rem;}
      .subtitle {color:#68766f; margin-top:-.55rem; margin-bottom:.2rem;}
      .step-kicker {font-size:.75rem; color:#75827b; letter-spacing:.08em;}
      .step-done {font-weight:700; color:#217a42;}
      .step-current {font-weight:700; color:#a45c00;}
      .step-pending {color:#768079;}
      .small-muted {color:#75827b; font-size:.85rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


def workspace() -> SessionWorkspace:
    if "_workspace" not in st.session_state:
        st.session_state._workspace = SessionWorkspace()
    current: SessionWorkspace = st.session_state._workspace
    current.activate()
    return current


CURRENT_WORKSPACE = workspace()


def reset_current_session() -> None:
    CURRENT_WORKSPACE.reset()
    for key in list(st.session_state.keys()):
        if key != "_workspace":
            del st.session_state[key]


def page_header(title: str, subtitle: str) -> None:
    st.markdown('<span class="demo-pill">PUBLIC DEMO · MOCK · SYNTHETIC</span>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<div class="subtitle">{subtitle}</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="notice"><b>临时合成数据：</b>每个浏览会话使用独立的临时库存、用户档案、知识库与实验数据。'
        '关闭会话或服务重启后数据可以重置。所有内容仅用于软件演示，<b>不构成医疗建议</b>。</div>',
        unsafe_allow_html=True,
    )


def rerun_agent(**updates: object) -> None:
    state = st.session_state.get("agent_state")
    if not state:
        return
    state.update(updates)
    st.session_state.agent_state = run_agent(state)


def flow_steps(state: dict | None) -> None:
    has_plan = bool(state and state.get("proposed_plan"))
    first_confirmed = bool(state and state.get("first_confirmation") is True)
    executed = bool(state and state.get("transaction_id"))
    values = [
        ("01", "需求输入", has_plan, not has_plan),
        ("02", "方案确认", first_confirmed, has_plan and not first_confirmed),
        ("03", "执行确认", executed, first_confirmed and not executed),
    ]
    for column, (number, label, done, current) in zip(st.columns(3), values):
        with column.container(border=True):
            css = "step-done" if done else "step-current" if current else "step-pending"
            status = "已完成" if done else "进行中" if current else "待开始"
            st.markdown(
                f'<div class="step-kicker">STEP {number}</div><div class="{css}">{label} · {status}</div>',
                unsafe_allow_html=True,
            )


def inventory_comparison(state: dict, usages: list[dict] | None = None) -> pd.DataFrame:
    plan = state.get("proposed_plan") or {}
    by_id = {item["canonical_item_id"]: item for item in plan.get("ingredients", [])}
    rows: list[dict] = []
    for usage in usages or state.get("actual_consumption") or []:
        ingredient = by_id.get(usage["canonical_item_id"])
        if not ingredient:
            continue
        before = float(ingredient["available_amount"])
        unit = ingredient["inventory_unit"]
        deduction = convert_amount(float(usage["amount"]), usage["unit"], unit)
        rows.append(
            {
                "食材": ingredient["display_name"],
                "扣减前": round(before, 2),
                "本次扣减": round(deduction, 2),
                "扣减后": round(before - deduction, 2),
                "单位": unit,
            }
        )
    return pd.DataFrame(rows)


def show_plan(state: dict) -> None:
    plan = state.get("proposed_plan")
    if not plan:
        return
    with st.container(border=True):
        st.subheader(plan["title"])
        st.caption(plan["description"])
        metrics = st.columns(4)
        metrics[0].metric("预计时长", f"{plan['estimated_minutes']} 分钟")
        metrics[1].metric("热量估算", f"{plan['calories_kcal']} kcal")
        metrics[2].metric("蛋白质", f"{plan['protein_g']} g")
        metrics[3].metric("脂肪", f"{plan['fat_g']} g")
        ingredients = pd.DataFrame(plan["ingredients"]).rename(
            columns={
                "display_name": "食材",
                "amount": "建议用量",
                "unit": "单位",
                "available_amount": "当前库存",
                "inventory_unit": "库存单位",
            }
        )
        st.dataframe(
            ingredients[["食材", "建议用量", "单位", "当前库存", "库存单位"]],
            use_container_width=True,
            hide_index=True,
        )
        left, right = st.columns(2)
        with left:
            st.markdown("**推荐理由**")
            for reason in plan["reasons"]:
                st.markdown(f"- {reason}")
        with right:
            st.markdown("**烹饪步骤**")
            for index, step in enumerate(plan["steps"], 1):
                st.markdown(f"{index}. {step}")
        if plan.get("warnings"):
            st.warning("；".join(plan["warnings"]))

    with st.expander("高级技术信息：结构化输出与检索证据"):
        st.write("Provider：", state.get("provider_note", "Mock Provider"))
        st.write("Pydantic 结构化计划已通过确定性库存、过敏原、单位和营养范围校验。")
        evidence = {row["id"]: row for row in state.get("retrieved_context", [])}
        selected = [evidence[item_id] for item_id in plan.get("retrieved_evidence_ids", []) if item_id in evidence]
        if selected:
            st.dataframe(
                pd.DataFrame(selected)[["title", "source_type", "score"]].rename(
                    columns={"title": "证据标题", "source_type": "来源类型", "score": "相关度"}
                ),
                use_container_width=True,
                hide_index=True,
            )


def meal_page() -> None:
    page_header("智能饮食 Agent", "从自然语言需求到两阶段确认，再到可撤销的库存事务。")
    state = st.session_state.get("agent_state")
    flow_steps(state)

    with st.container(border=True):
        st.markdown("#### 01 · 输入饮食需求")
        query = st.text_area(
            "饮食需求",
            value=st.session_state.get("query_text", ""),
            placeholder="例如：今晚想吃高蛋白、低脂、30分钟以内可以完成的食物。",
            height=100,
        )
        st.session_state.query_text = query
        action, hint = st.columns([1.35, 4])
        if action.button("生成结构化计划", type="primary", disabled=not query.strip(), use_container_width=True):
            st.session_state.agent_state = run_agent(
                initial_state(CURRENT_WORKSPACE.session_id, DEMO_USER_ID, query.strip())
            )
            st.rerun()
        hint.caption("Mock Provider 只生成候选计划；库存变化必须经过两次明确确认。")

    state = st.session_state.get("agent_state")
    if not state:
        st.info("输入需求开始演示。推荐示例：高蛋白、低脂、30 分钟以内。")
        return
    if state.get("error") and not state.get("proposed_plan"):
        st.error("当前需求未生成可执行计划，请修改描述后重试。")
        return

    show_plan(state)

    if state.get("proposed_plan") and state.get("first_confirmation") is None:
        with st.container(border=True):
            st.markdown("#### 02 · 第一次确认：接受推荐方案")
            st.write("这一步只确认方案，仍不会扣减库存。")
            accept, reject, _ = st.columns([1.5, 1, 3])
            if accept.button("确认方案并继续", type="primary", use_container_width=True):
                rerun_agent(first_confirmation=True)
                st.rerun()
            if reject.button("拒绝本次方案", use_container_width=True):
                rerun_agent(first_confirmation=False)
                st.rerun()

    elif (
        state.get("proposed_plan")
        and state.get("first_confirmation") is True
        and state.get("second_confirmation") is None
    ):
        with st.container(border=True):
            st.markdown("#### 03 · 第二次确认：核对实际用量并执行")
            st.caption("可以修改实际用量；下方展示扣减前、本次扣减和预计扣减后库存。")
            base = pd.DataFrame(
                state.get("actual_consumption")
                or [
                    {
                        "canonical_item_id": item["canonical_item_id"],
                        "amount": item["amount"],
                        "unit": item["unit"],
                    }
                    for item in state["proposed_plan"]["ingredients"]
                ]
            ).rename(columns={"canonical_item_id": "食材 ID", "amount": "实际用量", "unit": "单位"})
            edited = st.data_editor(
                base,
                num_rows="fixed",
                use_container_width=True,
                key="consumption_editor",
                disabled=["食材 ID"],
            )
            values = edited.rename(
                columns={"食材 ID": "canonical_item_id", "实际用量": "amount", "单位": "unit"}
            ).to_dict("records")
            st.markdown("**库存变化预览**")
            st.dataframe(inventory_comparison(state, values), use_container_width=True, hide_index=True)
            confirm, cancel, _ = st.columns([1.65, 1, 3])
            if confirm.button("确认用量并扣减库存", type="primary", use_container_width=True):
                rerun_agent(actual_consumption=values, second_confirmation=True)
                st.rerun()
            if cancel.button("取消执行", use_container_width=True):
                rerun_agent(actual_consumption=values, second_confirmation=False)
                st.rerun()

    state = st.session_state.get("agent_state")
    if state and state.get("transaction_id"):
        st.success("执行完成：库存已通过 SQLite 事务原子扣减，可在“库存与撤销”页面撤销。")
        with st.container(border=True):
            st.markdown("#### 执行结果 · 库存前后对比")
            st.dataframe(inventory_comparison(state), use_container_width=True, hide_index=True)
    elif state and state.get("final_message") and state.get("first_confirmation") is False:
        st.info("方案已拒绝，库存没有变化。")


def inventory_page() -> None:
    page_header("库存与撤销", "查看当前会话库存、事务前后变化，并撤销当前会话最近一次扣减。")
    with get_session() as session:
        inventory = list_inventory(session, DEMO_USER_ID)
        transactions = list_inventory_transaction_lines(session, DEMO_USER_ID)

    expired_count = sum(item["expired"] for item in inventory)
    near_expiry = sum(
        bool(item["expiration_date"] and 0 <= (item["expiration_date"] - date.today()).days <= 3)
        for item in inventory
    )
    metrics = st.columns(4)
    metrics[0].metric("库存条目", len(inventory))
    metrics[1].metric("可用条目", len(inventory) - expired_count)
    metrics[2].metric("3 天内到期", near_expiry)
    metrics[3].metric("已过期", expired_count)

    frame = pd.DataFrame(inventory)
    if not frame.empty:
        frame["状态"] = frame.apply(
            lambda row: "已过期"
            if row["expired"]
            else "临期"
            if row["expiration_date"] and 0 <= (row["expiration_date"] - date.today()).days <= 3
            else "正常",
            axis=1,
        )
        frame = frame.rename(
            columns={
                "canonical_name": "食材",
                "quantity": "数量",
                "unit": "单位",
                "expiration_date": "到期日",
                "location": "位置",
            }
        )
        st.dataframe(frame[["食材", "数量", "单位", "到期日", "位置", "状态"]], use_container_width=True, hide_index=True)

    st.subheader("当前会话的库存事务")
    if transactions:
        tx_frame = pd.DataFrame(transactions).rename(
            columns={
                "status": "状态",
                "created_at": "执行时间",
                "canonical_name": "食材",
                "quantity_before": "扣减前",
                "quantity_change": "变化量",
                "quantity_after": "扣减后",
                "unit": "单位",
            }
        )
        tx_frame["状态"] = tx_frame["状态"].map({"completed": "已完成", "reversed": "已撤销"}).fillna(tx_frame["状态"])
        st.dataframe(
            tx_frame[["执行时间", "食材", "扣减前", "变化量", "扣减后", "单位", "状态"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("当前会话还没有库存扣减记录。")

    if st.button("撤销当前会话最近一次扣减", disabled=not transactions):
        try:
            with get_session() as session:
                transaction = latest_executable_transaction(session, DEMO_USER_ID)
                if transaction is None:
                    st.info("当前会话没有可撤销的扣减。")
                else:
                    undo_transaction(session, transaction.id, CURRENT_WORKSPACE.session_id)
                    st.success("已撤销最近一次扣减，当前会话库存已恢复。")
                    st.rerun()
        except ValueError:
            st.error("撤销未完成，请刷新后重试。")


def knowledge_page() -> None:
    page_header("私域知识检索", "对当前会话的合成偏好、历史反馈与一般饮食知识执行本地 TF-IDF 检索。")
    with get_session() as session:
        rows = list_knowledge(session, DEMO_USER_ID)
    st.dataframe(
        pd.DataFrame(rows)[["title", "content", "source_type", "tags"]].rename(
            columns={"title": "标题", "content": "内容", "source_type": "来源类型", "tags": "标签"}
        ),
        use_container_width=True,
        hide_index=True,
    )
    query = st.text_input("检索问题", placeholder="例如：鸡胸肉和番茄偏好")
    if query:
        results = retrieve(query, rows)
        if results:
            st.subheader("检索结果")
            st.dataframe(
                pd.DataFrame(results)[["title", "content", "source_type", "score"]].rename(
                    columns={"title": "标题", "content": "证据内容", "source_type": "来源类型", "score": "相关度"}
                ),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("没有达到最低相关度的合成知识条目。")


def trace_page() -> None:
    page_header("Agent 执行轨迹", "用可读的节点摘要展示 LangGraph 路由、校验、确认与事务执行。")
    state = st.session_state.get("agent_state")
    if not state:
        st.info("请先在“智能饮食 Agent”页面运行一次流程。")
        return
    events = state.get("audit_events", [])
    trace = pd.DataFrame(
        [
            {
                "序号": index,
                "节点": event.get("node_name"),
                "执行摘要": event.get("summary"),
                "重试": event.get("retry_count", 0),
            }
            for index, event in enumerate(events, 1)
        ]
    )
    metrics = st.columns(4)
    metrics[0].metric("执行节点", len(events))
    metrics[1].metric("当前节点", state.get("current_node", "-"))
    metrics[2].metric("重试次数", state.get("retry_count", 0))
    metrics[3].metric("校验问题", len(state.get("validation_errors", [])))
    st.dataframe(trace, use_container_width=True, hide_index=True)
    with st.expander("高级技术信息：路由与确定性校验"):
        requirements = state.get("normalized_requirements", {})
        st.write(
            {
                "识别意图": state.get("intent"),
                "烹饪时限": requirements.get("max_minutes"),
                "高蛋白": requirements.get("high_protein"),
                "低脂": requirements.get("low_fat"),
                "校验问题数": len(state.get("validation_errors", [])),
                "Provider": "Mock",
            }
        )


def experiment_page() -> None:
    page_header("Prompt 合成实验", "对 20 个 synthetic/sample 案例运行可复现的规则模拟对比。")
    st.warning("这不是真实用户 A/B 测试，不代表满意度、留存、转化率或业务收益。")
    if st.button("运行合成 A/B 实验", type="primary"):
        with st.spinner("正在计算合成实验指标..."):
            st.session_state.ab_results = run_synthetic_experiment()
    results = st.session_state.get("ab_results")
    if results:
        summary = pd.DataFrame(summarize_results(results)).rename(
            columns={
                "variant": "Variant",
                "cases": "案例数",
                "pydantic_parse_rate": "结构化解析率",
                "validation_pass_rate": "规则通过率",
                "hallucinated_food_count": "幻觉食材数",
                "avg_retry_count": "平均重试",
                "avg_latency_ms": "平均延迟(ms)",
                "needs_clarification_count": "需澄清案例",
                "executable_rate": "可执行率",
            }
        )
        st.dataframe(summary, use_container_width=True, hide_index=True)
    else:
        st.info("点击按钮运行。结果仅来自当前代码与合成案例。")
    with st.expander("高级技术信息：Prompt Variant 与指标边界"):
        st.code(f"Variant A: {PROMPTS['A']}\n\nVariant B: {PROMPTS['B']}")
        st.caption("仅统计结构化解析、规则校验、幻觉食材、重试、延迟、澄清与可执行性。")


def about_page() -> None:
    page_header("架构与安全说明", "公开版的会话隔离、数据边界与可执行安全设计。")
    left, right = st.columns(2)
    with left.container(border=True):
        st.markdown("#### 执行架构")
        st.markdown(
            "- LangGraph：编排需求、检索、校验、确认与执行节点\n"
            "- Mock Provider：生成 Pydantic 结构化候选计划\n"
            "- Python guardrails：过滤过期、过敏、未知单位与库存不足\n"
            "- SQLite 事务：两次确认后原子扣减并支持撤销"
        )
    with right.container(border=True):
        st.markdown("#### 公开演示边界")
        st.markdown(
            "- 每个浏览会话使用独立临时 SQLite 数据库\n"
            "- 新会话从相同 synthetic/sample 基线开始\n"
            "- 不连接外部模型、真实用户系统或医疗系统\n"
            "- 服务重启后临时数据可以重置\n"
            "- 一般饮食信息不构成医疗建议"
        )
    st.subheader("核心安全门")
    st.markdown("**需求输入 → 结构化方案 → 确定性校验 → 第一次确认 → 实际用量 → 第二次确认 → 事务扣减 → 可撤销**")


PAGES = {
    "智能饮食 Agent": meal_page,
    "库存与撤销": inventory_page,
    "私域知识检索": knowledge_page,
    "Agent 执行轨迹": trace_page,
    "Prompt 合成实验": experiment_page,
    "架构与安全说明": about_page,
}

with st.sidebar:
    st.title("🥗 Auto-LifeOS")
    st.caption("Isolated Streamlit Public Demo")
    st.markdown('<span class="demo-pill">MOCK ONLY</span>', unsafe_allow_html=True)
    st.caption("临时 synthetic/sample 数据\n\n不构成医疗建议")
    st.divider()
    selected_page = st.radio("演示导航", list(PAGES), label_visibility="collapsed")
    st.divider()
    if st.button("重置当前会话", use_container_width=True):
        reset_current_session()
        st.rerun()
    st.caption("只重置当前浏览会话，不影响其他访问者。")

try:
    PAGES[selected_page]()
except Exception:
    st.error("当前操作未完成。请重试，或使用侧边栏重置当前会话。")

