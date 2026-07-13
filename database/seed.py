from __future__ import annotations

from datetime import date, timedelta
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import CanonicalFood, FoodAlias, PantryItem, PrivateKnowledge, User, UserProfile

DEMO_USER_ID = "demo-user"

FOODS = [
    ("chicken_breast", "鸡胸肉", "蛋白质", "g", 165, 31, 0, 3.6),
    ("tomato", "番茄", "蔬菜", "g", 18, 0.9, 3.9, 0.2),
    ("rice", "大米", "主食", "g", 130, 2.7, 28, 0.3),
    ("egg", "鸡蛋", "蛋白质", "个", 72, 6.3, 0.4, 4.8),
    ("broccoli", "西兰花", "蔬菜", "g", 34, 2.8, 7, 0.4),
    ("oats", "燕麦", "主食", "g", 389, 17, 66, 7),
    ("milk", "牛奶", "饮品", "ml", 61, 3.2, 4.8, 3.3),
    ("peanut_butter", "花生酱", "调味", "g", 588, 25, 20, 50),
    ("yogurt", "酸奶", "饮品", "g", 63, 5.3, 7, 1.5),
]
ALIASES = {
    "西红柿": "tomato", "番茄": "tomato", "tomato": "tomato",
    "鸡胸": "chicken_breast", "鸡胸肉": "chicken_breast", "chicken breast": "chicken_breast",
    "蛋": "egg", "鸡蛋": "egg", "egg": "egg",
    "燕麦片": "oats", "燕麦": "oats", "oats": "oats",
    "broccoli": "broccoli", "西兰花": "broccoli", "米饭": "rice", "大米": "rice",
    "牛奶": "milk", "milk": "milk", "花生酱": "peanut_butter", "酸奶": "yogurt",
}


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
        ))
    for alias, food_id in ALIASES.items():
        session.add(FoodAlias(alias=alias.lower(), canonical_food_id=food_id))
    tomorrow = date.today() + timedelta(days=1)
    expired = date.today() - timedelta(days=1)
    pantry = [
        ("chicken_breast", 1500, "g", tomorrow, "冷藏"), ("tomato", 400, "g", tomorrow, "冷藏"),
        ("rice", 2000, "g", None, "干货柜"), ("egg", 8, "个", tomorrow, "冷藏"),
        ("broccoli", 600, "g", tomorrow, "冷藏"), ("oats", 1000, "g", None, "干货柜"),
        ("milk", 1500, "ml", tomorrow, "冷藏"), ("peanut_butter", 200, "g", None, "干货柜"),
        ("yogurt", 1, "个", expired, "冷藏"),
    ]
    for food_id, quantity, unit, expiry, location in pantry:
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

