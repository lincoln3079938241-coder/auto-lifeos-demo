from __future__ import annotations

from datetime import date, timedelta
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import CanonicalFood, FoodAlias, PantryItem, PrivateKnowledge, User, UserProfile

DEMO_USER_ID = "demo-user"

FOODS = [
    ("rice", "大米", "主食", "g", 130, 2.7, 28, 0.3, False),
    ("noodles", "面条", "主食", "g", 138, 4.5, 25, 2.1, False),
    ("oats", "燕麦", "主食", "g", 389, 17, 66, 7, False),
    ("whole_wheat_bread", "全麦面包", "主食", "g", 247, 13, 41, 4.2, False),
    ("potato", "土豆", "主食", "g", 77, 2, 17, 0.1, False),
    ("sweet_potato", "红薯", "主食", "g", 86, 1.6, 20, 0.1, False),
    ("corn", "玉米", "主食", "g", 96, 3.4, 21, 1.5, False),
    ("chicken_breast", "鸡胸肉", "肉蛋奶", "g", 165, 31, 0, 3.6, False),
    ("chicken_thigh", "鸡腿肉", "肉蛋奶", "g", 209, 26, 0, 10.9, False),
    ("egg", "鸡蛋", "肉蛋奶", "个", 72, 6.3, 0.4, 4.8, False),
    ("lean_pork", "瘦猪肉", "肉蛋奶", "g", 143, 26, 0, 3.5, False),
    ("beef", "牛肉", "肉蛋奶", "g", 250, 26, 0, 15, False),
    ("shrimp", "虾仁", "肉蛋奶", "g", 99, 24, 0.2, 0.3, False),
    ("fish", "鱼肉", "肉蛋奶", "g", 120, 22, 0, 3.5, False),
    ("milk", "牛奶", "肉蛋奶", "ml", 61, 3.2, 4.8, 3.3, False),
    ("plain_yogurt", "无糖酸奶", "肉蛋奶", "g", 63, 5.3, 7, 1.5, False),
    ("firm_tofu", "老豆腐", "豆制品", "g", 90, 10, 2.5, 5, False),
    ("soft_tofu", "嫩豆腐", "豆制品", "g", 56, 5, 2, 3, False),
    ("tofu_dry", "豆干", "豆制品", "g", 140, 16, 4, 7, False),
    ("soy_milk", "无糖豆浆", "豆制品", "ml", 33, 3.3, 1.8, 1.8, False),
    ("tomato", "番茄", "蔬菜", "g", 18, 0.9, 3.9, 0.2, False),
    ("broccoli", "西兰花", "蔬菜", "g", 34, 2.8, 7, 0.4, False),
    ("spinach", "菠菜", "蔬菜", "g", 23, 2.9, 3.6, 0.4, False),
    ("greens", "青菜", "蔬菜", "g", 18, 1.5, 3, 0.2, False),
    ("lettuce", "生菜", "蔬菜", "g", 15, 1.4, 2.9, 0.2, False),
    ("cucumber", "黄瓜", "蔬菜", "g", 15, 0.7, 3.6, 0.1, False),
    ("carrot", "胡萝卜", "蔬菜", "g", 41, 0.9, 10, 0.2, False),
    ("onion", "洋葱", "蔬菜", "g", 40, 1.1, 9.3, 0.1, False),
    ("cabbage", "白菜", "蔬菜", "g", 16, 1.2, 3.2, 0.2, False),
    ("bell_pepper", "彩椒", "蔬菜", "g", 31, 1, 6, 0.3, False),
    ("green_pepper", "青椒", "蔬菜", "g", 22, 1, 5.4, 0.2, False),
    ("mushroom", "蘑菇", "蔬菜", "g", 22, 3.1, 3.3, 0.3, False),
    ("shiitake", "香菇", "蔬菜", "g", 34, 2.2, 6.8, 0.5, False),
    ("eggplant", "茄子", "蔬菜", "g", 25, 1, 6, 0.2, False),
    ("apple", "苹果", "水果", "g", 52, 0.3, 14, 0.2, False),
    ("banana", "香蕉", "水果", "g", 89, 1.1, 23, 0.3, False),
    ("orange", "橙子", "水果", "g", 47, 0.9, 12, 0.1, False),
    ("blueberry", "蓝莓", "水果", "g", 57, 0.7, 14, 0.3, False),
    ("garlic", "蒜", "基础调味料", "g", 149, 6.4, 33, 0.5, True),
    ("ginger", "姜", "基础调味料", "g", 80, 1.8, 18, 0.8, True),
    ("scallion", "葱", "基础调味料", "g", 32, 1.8, 7, 0.2, True),
    ("cooking_oil", "食用油", "基础调味料", "ml", 884, 0, 0, 100, True),
    ("soy_sauce", "生抽", "基础调味料", "ml", 53, 8, 4.9, 0.1, True),
    ("vinegar", "醋", "基础调味料", "ml", 18, 0, 0.9, 0, True),
    ("salt", "盐", "基础调味料", "g", 0, 0, 0, 0, True),
    ("black_pepper", "黑胡椒", "基础调味料", "g", 251, 10, 64, 3.3, True),
]
ALIASES = {
    "大米": "rice", "米": "rice", "米饭": "rice", "rice": "rice",
    "面条": "noodles", "面": "noodles", "挂面": "noodles", "noodles": "noodles",
    "燕麦": "oats", "燕麦片": "oats", "oat": "oats", "oats": "oats",
    "全麦面包": "whole_wheat_bread", "全麦吐司": "whole_wheat_bread", "whole wheat bread": "whole_wheat_bread",
    "土豆": "potato", "马铃薯": "potato", "potato": "potato",
    "红薯": "sweet_potato", "地瓜": "sweet_potato", "sweet potato": "sweet_potato",
    "玉米": "corn", "corn": "corn",
    "鸡胸肉": "chicken_breast", "鸡胸": "chicken_breast", "chicken breast": "chicken_breast",
    "鸡腿肉": "chicken_thigh", "鸡腿": "chicken_thigh", "chicken thigh": "chicken_thigh",
    "鸡蛋": "egg", "蛋": "egg", "egg": "egg",
    "瘦猪肉": "lean_pork", "猪瘦肉": "lean_pork", "lean pork": "lean_pork",
    "牛肉": "beef", "beef": "beef",
    "虾仁": "shrimp", "虾": "shrimp", "shrimp": "shrimp", "prawns": "shrimp",
    "鱼肉": "fish", "鱼": "fish", "fish": "fish",
    "牛奶": "milk", "奶": "milk", "milk": "milk",
    "无糖酸奶": "plain_yogurt", "酸奶": "plain_yogurt", "yogurt": "plain_yogurt",
    "老豆腐": "firm_tofu", "豆腐": "firm_tofu", "北豆腐": "firm_tofu", "tofu": "firm_tofu",
    "嫩豆腐": "soft_tofu", "南豆腐": "soft_tofu", "soft tofu": "soft_tofu",
    "豆干": "tofu_dry", "香干": "tofu_dry", "dried tofu": "tofu_dry",
    "无糖豆浆": "soy_milk", "豆浆": "soy_milk", "soy milk": "soy_milk",
    "番茄": "tomato", "西红柿": "tomato", "tomato": "tomato",
    "西兰花": "broccoli", "花椰菜": "broccoli", "broccoli": "broccoli",
    "菠菜": "spinach", "spinach": "spinach",
    "青菜": "greens", "小青菜": "greens", "上海青": "greens", "greens": "greens",
    "生菜": "lettuce", "lettuce": "lettuce",
    "黄瓜": "cucumber", "青瓜": "cucumber", "cucumber": "cucumber",
    "胡萝卜": "carrot", "红萝卜": "carrot", "carrot": "carrot",
    "洋葱": "onion", "onion": "onion",
    "白菜": "cabbage", "大白菜": "cabbage", "cabbage": "cabbage",
    "彩椒": "bell_pepper", "甜椒": "bell_pepper", "bell pepper": "bell_pepper",
    "青椒": "green_pepper", "green pepper": "green_pepper",
    "蘑菇": "mushroom", "口蘑": "mushroom", "mushroom": "mushroom",
    "香菇": "shiitake", "shiitake": "shiitake",
    "茄子": "eggplant", "eggplant": "eggplant",
    "苹果": "apple", "apple": "apple", "香蕉": "banana", "banana": "banana",
    "橙子": "orange", "橙": "orange", "orange": "orange", "蓝莓": "blueberry", "blueberries": "blueberry",
    "蒜": "garlic", "大蒜": "garlic", "garlic": "garlic", "姜": "ginger", "生姜": "ginger", "ginger": "ginger",
    "葱": "scallion", "小葱": "scallion", "scallion": "scallion",
    "食用油": "cooking_oil", "油": "cooking_oil", "cooking oil": "cooking_oil",
    "生抽": "soy_sauce", "酱油": "soy_sauce", "soy sauce": "soy_sauce",
    "醋": "vinegar", "vinegar": "vinegar", "盐": "salt", "食盐": "salt", "salt": "salt",
    "黑胡椒": "black_pepper", "胡椒": "black_pepper", "black pepper": "black_pepper",
}


def baseline_pantry() -> list[tuple[str, float, str, date | None, str]]:
    """Return a fresh synthetic inventory baseline with dates relative to today."""
    tomorrow = date.today() + timedelta(days=1)
    expired = date.today() - timedelta(days=1)
    in_five_days = date.today() + timedelta(days=5)
    return [
        ("rice", 2000, "g", None, "干货柜"), ("noodles", 800, "g", None, "干货柜"),
        ("oats", 1000, "g", None, "干货柜"), ("whole_wheat_bread", 500, "g", in_five_days, "冷藏"),
        ("chicken_breast", 1500, "g", tomorrow, "冷藏"), ("egg", 8, "个", tomorrow, "冷藏"),
        ("milk", 1500, "ml", tomorrow, "冷藏"), ("firm_tofu", 600, "g", in_five_days, "冷藏"),
        ("tomato", 400, "g", tomorrow, "冷藏"), ("broccoli", 600, "g", tomorrow, "冷藏"),
        ("greens", 500, "g", in_five_days, "冷藏"), ("cucumber", 500, "g", in_five_days, "冷藏"),
        ("carrot", 500, "g", in_five_days, "冷藏"), ("onion", 600, "g", None, "阴凉处"),
        ("mushroom", 400, "g", in_five_days, "冷藏"), ("banana", 600, "g", in_five_days, "常温"),
        ("soy_sauce", 500, "ml", None, "调味柜"), ("cooking_oil", 1000, "ml", None, "调味柜"),
        ("salt", 300, "g", None, "调味柜"), ("plain_yogurt", 200, "g", expired, "冷藏"),
    ]


def seed_database(session: Session) -> None:
    if session.get(User, DEMO_USER_ID):
        return
    session.add(User(id=DEMO_USER_ID, name="Demo User"))
    session.add(UserProfile(
        user_id=DEMO_USER_ID, height_cm=170, weight_kg=65,
        goal="控制体脂、提高蛋白质摄入", daily_calorie_min=500, daily_calorie_max=650,
        allergies_json=json.dumps(["花生"], ensure_ascii=False),
        avoid_foods_json=json.dumps(["香菜"], ensure_ascii=False),
        preferences_json=json.dumps(["鸡肉", "番茄", "米饭", "燕麦", "30分钟以内"], ensure_ascii=False),
    ))
    for row in FOODS:
        session.add(CanonicalFood(
            id=row[0], canonical_name=row[1], category=row[2], default_unit=row[3],
            calories_per_100g=row[4], protein_per_100g=row[5], carbs_per_100g=row[6], fat_per_100g=row[7],
            pantry_staple=row[8],
        ))
    for alias, food_id in ALIASES.items():
        session.add(FoodAlias(alias=alias.lower(), canonical_food_id=food_id))
    for food_id, quantity, unit, expiry, location in baseline_pantry():
        session.add(PantryItem(user_id=DEMO_USER_ID, canonical_food_id=food_id, quantity=quantity,
                               unit=unit, expiration_date=expiry, location=location))
    knowledge = [
        ("历史偏好", "用户过去更愿意接受鸡胸肉配番茄和米饭的晚餐，口味偏清淡。", "history", "偏好,鸡肉,番茄"),
        ("历史反馈", "用户反馈：20 分钟内完成、蛋白质明确标注的方案更容易执行。", "feedback", "时间,蛋白质"),
        ("一般营养提示", "蛋白质可来自瘦肉、鸡蛋和奶制品；总量应结合个人需求安排。该信息不是医疗诊断或治疗建议。", "nutrition", "蛋白质,免责声明"),
        ("烹饪替代规则", "鸡胸肉不足时可提示鸡蛋替代；过期食材不得作为可执行计划的食材。", "rule", "替代,过期"),
    ]
    for title, content, source_type, tags in knowledge:
        session.add(PrivateKnowledge(user_id=DEMO_USER_ID, title=title, content=content,
                                     source_type=source_type, tags=tags))
    session.commit()
