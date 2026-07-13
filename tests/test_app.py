from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from agent.graph import run_agent
from agent.state import initial_state
from database.repositories import list_inventory
from database.seed import DEMO_USER_ID
from database.session import get_session


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
QUERY = "今晚想吃高蛋白、低脂、30分钟以内可以完成的食物。"
EXAMPLES = {
    "高蛋白低脂晚餐": QUERY,
    "简单营养早餐": "请推荐一份简单、有蛋白质、20分钟以内可以完成的早餐。",
    "使用现有食材": "请根据家里现有的演示食材，推荐一份容易完成的饭菜。",
}


def button(app: AppTest, label: str):
    return next(item for item in app.button if item.label == label)


def quantities(app: AppTest) -> dict[str, float]:
    app.session_state["_workspace"].activate()
    with get_session() as session:
        return {row["canonical_item_id"]: row["quantity"] for row in list_inventory(session, DEMO_USER_ID)}


def close(app: AppTest) -> None:
    app.session_state["_workspace"].close()


def test_first_visit_is_plain_and_actionable() -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    try:
        assert not app.exception
        text = " ".join(element.value for element in app.markdown)
        assert "今天吃什么？让智能助手帮你想一想" in text
        assert "无需登录" in text
        assert "使用虚拟演示数据" in text
        assert "不构成医疗建议" in text
        assert "你今天想吃什么？" in text
        assert not any(term in text for term in ["LangGraph", "RAG", "Prompt", "SQLite", "Mock Provider"])
        assert button(app, "帮我推荐").disabled
        assert not any(item.label == "这个方案可以" for item in app.button)
        assert not any(item.label == "确认并更新演示库存" for item in app.button)
    finally:
        close(app)


def test_all_examples_fill_the_input() -> None:
    for label, expected in EXAMPLES.items():
        app = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
        try:
            button(app, label).click().run()
            assert app.text_area[0].value == expected
            assert not button(app, "帮我推荐").disabled
        finally:
            close(app)


def test_change_plan_returns_to_edit_without_inventory_change() -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    try:
        app.text_area[0].input(QUERY).run()
        button(app, "帮我推荐").click().run()
        assert quantities(app)["chicken_breast"] == 1500
        assert any("番茄鸡胸饭" in title.value for title in app.header)
        assert not any(item.label == "确认并更新演示库存" for item in app.button)
        button(app, "换一个方案").click().run()
        assert app.session_state["agent_state"] is None
        assert quantities(app)["chicken_breast"] == 1500
        assert any("演示库存没有变化" in info.value for info in app.info)
    finally:
        close(app)


def test_guided_flow_keeps_inventory_until_second_confirmation_and_can_undo() -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    try:
        app.text_area[0].input(QUERY).run()
        button(app, "帮我推荐").click().run()
        assert quantities(app)["chicken_breast"] == 1500
        assert any(item.label == "这个方案可以" for item in app.button)
        assert not any(item.label == "确认并更新演示库存" for item in app.button)

        button(app, "这个方案可以").click().run()
        assert quantities(app)["chicken_breast"] == 1500
        assert any(item.label == "确认并更新演示库存" for item in app.button)
        assert not any(item.label == "这个方案可以" for item in app.button)
        assert len(app.number_input) == 3
        app.number_input[0].set_value(170).run()

        button(app, "确认并更新演示库存").click().run()
        assert quantities(app)["chicken_breast"] == 1330
        assert quantities(app)["tomato"] == 200
        assert quantities(app)["rice"] == 1850
        assert any("已完成，本次演示库存已更新" in message.value for message in app.success)
        assert app.session_state["agent_state"]["transaction_id"]
    finally:
        close(app)


def test_completion_undo_button_restores_inventory() -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    try:
        workspace = app.session_state["_workspace"]
        workspace.activate()
        state = run_agent(initial_state(workspace.session_id, DEMO_USER_ID, QUERY))
        state["first_confirmation"] = True
        state = run_agent(state)
        state["second_confirmation"] = True
        state = run_agent(state)
        app.session_state["agent_state"] = state
        app.session_state["meal_query"] = QUERY
        app.session_state["completion_undone"] = False
        app.run()

        assert quantities(app)["chicken_breast"] == 1320
        assert any("已完成，本次演示库存已更新" in message.value for message in app.success)
        button(app, "撤销本次更新").click().run()
        assert quantities(app)["chicken_breast"] == 1500
        assert quantities(app)["tomato"] == 400
        assert quantities(app)["rice"] == 2000
        assert any("已撤销，本次使用的食材已经恢复" in message.value for message in app.success)

        button(app, "再推荐一份").click().run()
        assert app.session_state["agent_state"] is None
        assert app.text_area[0].value == ""
    finally:
        close(app)


def test_technical_content_remains_under_project_page() -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    try:
        app.radio[0].set_value("了解项目原理").run()
        labels = {item.label for item in app.expander}
        assert "这个项目解决什么问题" in labels
        assert "系统是怎样得出推荐的" in labels
        assert "我的饮食习惯（知识检索）" in labels
        assert "系统是怎样得出结果的（Agent Trace）" in labels
        assert "两种推荐方式对比（Prompt A/B）" in labels
        assert "工程测试" in labels
        assert "安全与限制" in labels
        button(app, "运行两种推荐方式对比").click().run()
        assert app.session_state["ab_results"]
        assert len(app.session_state["ab_results"]) == 40
    finally:
        close(app)
