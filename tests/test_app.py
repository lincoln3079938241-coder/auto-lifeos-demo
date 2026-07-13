from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from agent.graph import run_agent
from agent.state import initial_state
from database.repositories import list_inventory
from database.seed import DEMO_USER_ID
from database.session import get_session
from services.units import convert_amount


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
QUERY = "今晚想吃高蛋白、低脂、30分钟以内可以完成的食物。"
EXAMPLES = {
    "高蛋白低脂晚餐": QUERY,
    "简单营养早餐": "请推荐一份简单营养早餐。",
    "快手家常菜": "请推荐一道30分钟以内可以完成的快手家常菜。",
    "根据快过期食材推荐": "请优先使用快过期的食材推荐一份饭菜。",
    "素食方案": "我今天想吃素食，请推荐一份30分钟以内的方案。",
    "只使用现有食材": "请只使用当前演示库存推荐一份饭菜。",
}


def button(app: AppTest, label: str):
    return next(item for item in app.button if item.label == label)


def button_key(app: AppTest, key: str):
    return next(item for item in app.button if item.key == key)


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
        assert button(app, "先调整演示库存")
        assert not any(item.label == "这个方案可以" for item in app.button)
        assert not any(item.label == "确认并更新演示库存" for item in app.button)
    finally:
        close(app)


def test_home_secondary_entry_opens_inventory_page() -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    try:
        button(app, "先调整演示库存").click().run()
        assert app.radio[0].value == "演示库存"
        captions = " ".join(item.value for item in app.caption)
        assert "智能助手会根据修改后的库存重新推荐" in captions
    finally:
        close(app)


def test_inventory_page_add_and_modify() -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    try:
        app.radio[0].set_value("演示库存").run()
        by_label = {item.label: item for item in app.text_input}
        by_label["食材名称"].input("鲍鱼")
        by_label["当前数量"].input("500")
        by_label["保质期"].input("")
        by_label["存放位置"].input("冷藏")
        button(app, "添加食材").click().run()
        assert any("当前菜谱库暂无对应方案" in item.value for item in app.success)

        app.session_state["_workspace"].activate()
        with get_session() as session:
            custom = next(row for row in list_inventory(session, DEMO_USER_ID) if row["canonical_name"] == "鲍鱼")
        item_id = custom["pantry_item_id"]

        button_key(app, f"edit_inventory_{item_id}").click().run()
        next(item for item in app.text_input if item.key == f"quantity_{item_id}").input("650")
        next(item for item in app.text_input if item.key == f"location_{item_id}").input("冷冻")
        button(app, "保存修改").click().run()
        assert quantities(app)[custom["canonical_item_id"]] == 650
    finally:
        close(app)


def test_inventory_search_and_alias_duplicate_prompt() -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    try:
        app.radio[0].set_value("演示库存").run()
        next(item for item in app.text_input if item.label == "搜索食材").input("鸡胸").run()
        page_text = " ".join(item.value for item in app.markdown)
        assert "鸡胸肉" in page_text
        assert "番茄" not in page_text

        next(item for item in app.text_input if item.label == "搜索食材").input("").run()
        by_label = {item.label: item for item in app.text_input}
        by_label["食材名称"].input("西红柿")
        by_label["当前数量"].input("50")
        by_label["保质期"].input("")
        by_label["存放位置"].input("冷藏")
        button(app, "添加食材").click().run()
        assert any("库存中已经存在番茄，是否将本次数量增加到现有库存" in item.value for item in app.warning)
        assert button(app, "合并数量")
        assert button(app, "取消添加")
        assert quantities(app)["tomato"] == 400
    finally:
        close(app)


def test_inventory_page_confirms_delete() -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    try:
        app.radio[0].set_value("演示库存").run()
        workspace = app.session_state["_workspace"]
        workspace.activate()
        with get_session() as session:
            from services.inventory_editor import add_inventory_item

            result = add_inventory_item(
                session, workspace.session_id, DEMO_USER_ID, name="鲍鱼", quantity=500,
                unit="g", expiration_date=None, location="冷藏"
            )
        app.run()
        with get_session() as session:
            custom = next(row for row in list_inventory(session, DEMO_USER_ID) if row["canonical_name"] == "鲍鱼")
        item_id = custom["pantry_item_id"]
        button_key(app, f"delete_inventory_{item_id}").click().run()
        assert any("确定从当前演示库存中删除这个食材吗" in item.value for item in app.warning)
        button_key(app, f"confirm_delete_{item_id}").click().run()
        assert result["canonical_item_id"] not in quantities(app)
    finally:
        close(app)


def test_inventory_page_restores_baseline() -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    try:
        app.radio[0].set_value("演示库存").run()
        workspace = app.session_state["_workspace"]
        workspace.activate()
        with get_session() as session:
            from services.inventory_editor import add_inventory_item, update_inventory_item

            add_inventory_item(
                session, workspace.session_id, DEMO_USER_ID, name="鲍鱼", quantity=500,
                unit="g", expiration_date=None, location="冷藏"
            )
            chicken = next(row for row in list_inventory(session, DEMO_USER_ID)
                           if row["canonical_item_id"] == "chicken_breast")
            update_inventory_item(
                session, workspace.session_id, DEMO_USER_ID, chicken["pantry_item_id"],
                quantity=300, unit="g", expiration_date=None, location="冷藏"
            )
        app.run()
        button(app, "恢复初始演示库存").click().run()
        assert len(quantities(app)) == 20
        assert quantities(app)["chicken_breast"] == 1500
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
        assert app.session_state["agent_state"]["proposed_plan"]["title"]
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
        plan = app.session_state["agent_state"]["proposed_plan"]
        before = quantities(app)
        assert len(app.number_input) == len(plan["ingredients"])
        changed_amount = max(1.0, float(plan["ingredients"][0]["amount"]) - 10)
        app.number_input[0].set_value(changed_amount).run()

        button(app, "确认并更新演示库存").click().run()
        after = quantities(app)
        for index, ingredient in enumerate(plan["ingredients"]):
            used = changed_amount if index == 0 else float(ingredient["amount"])
            converted = convert_amount(used, ingredient["unit"], ingredient["inventory_unit"])
            assert after[ingredient["canonical_item_id"]] == pytest.approx(
                before[ingredient["canonical_item_id"]] - converted
            )
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

        baseline = quantities(app)
        assert baseline["chicken_breast"] < 1500
        assert any("已完成，本次演示库存已更新" in message.value for message in app.success)
        button(app, "撤销本次更新").click().run()
        assert quantities(app)["chicken_breast"] == 1500
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
