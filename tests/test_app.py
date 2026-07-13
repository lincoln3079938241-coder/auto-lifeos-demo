from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_app_starts_and_shows_public_boundaries() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=20)
    app.run()
    assert not app.exception
    text = " ".join(element.value for element in app.markdown)
    assert "PUBLIC DEMO" in text
    assert "临时合成数据" in text
    assert "不构成医疗建议" in text
    assert app.button[0].label == "生成结构化计划"
    app.session_state["_workspace"].close()


def test_app_core_flow_generates_confirms_and_deducts() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=30).run()
    app.text_area[0].input("今晚想吃高蛋白、低脂、30分钟以内可以完成的食物。").run()
    next(button for button in app.button if button.label == "生成结构化计划").click().run()
    assert any("番茄鸡胸饭" in title.value for title in app.subheader)
    next(button for button in app.button if button.label == "确认方案并继续").click().run()
    assert any(button.label == "确认用量并扣减库存" for button in app.button)
    next(button for button in app.button if button.label == "确认用量并扣减库存").click().run()
    assert any("执行完成" in message.value for message in app.success)
    assert app.session_state["agent_state"]["transaction_id"]
    app.session_state["_workspace"].close()
