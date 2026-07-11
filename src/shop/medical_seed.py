"""Сид медицинского дерева (Фаза 1): концепты-категории + малый справочник.

Идемпотентно (по code): повторный запуск ничего не дублирует. Всё — данные
на существующем ядре, новых таблиц нет.

- Концепты = Category (symptom с 11-слотовой схемой, medication, allergy,
  heredity, illness/injury с FSM + required + red_flags в value, ...).
- Справочные элементы = Entity, якорь objectid -> корневая категория 'medical'
  (домен reference наследуется), вид задаётся полем category.
- Названия пока в поле name (RU); Translation подключим, когда понадобится
  второй язык (YAGNI).
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import tables

# 11-слотовая схема разбора симптома (OPQRST/SOCRATES + расширение)
SYMPTOM_SCHEMA = [
    {"code": "onset",       "label": "Начало"},
    {"code": "site",        "label": "Локализация"},
    {"code": "character",   "label": "Характер"},
    {"code": "severity",    "label": "Интенсивность (0–10)"},
    {"code": "time",        "label": "Временной профиль"},
    {"code": "provocation", "label": "Провоцирующие факторы"},
    {"code": "palliation",  "label": "Облегчающие факторы"},
    {"code": "radiation",   "label": "Иррадиация"},
    {"code": "associations", "label": "Сопутствующие симптомы"},
    {"code": "impact",      "label": "Влияние на жизнь"},
    {"code": "previous",    "label": "Предыдущие эпизоды"},
]

# концепты: code -> (name, value-конфиг)
CONCEPTS = {
    "symptom":     ("Симптом", {"schema": SYMPTOM_SCHEMA}),
    "medication":  ("Лекарство", {}),
    "allergy":     ("Аллергия", {}),
    "heredity":    ("Наследственность", {}),
    "risk_factor": ("Фактор риска", {}),
    "illness": ("Болезнь", {
        "fsm": {
            "states": ["anamnesis", "diagnosis", "treatment", "remission", "recovered"],
            "initial": "anamnesis",
            "transitions": [
                {"event": "diagnose", "source": "anamnesis",  "dest": "diagnosis"},
                {"event": "treat",    "source": "diagnosis",  "dest": "treatment"},
                {"event": "recover",  "source": "treatment",  "dest": "recovered"},
                {"event": "remit",    "source": "treatment",  "dest": "remission"},
                {"event": "relapse",  "source": "remission",  "dest": "treatment"},
            ],
        },
        # секции полноты: {category-код концепта, scope: episode|patient}
        "required": [
            {"category": "symptom",    "scope": "episode"},
            {"category": "medication", "scope": "patient"},
            {"category": "allergy",    "scope": "patient"},
            {"category": "heredity",   "scope": "patient"},
        ],
        "red_flags": ["acs"],   # обработчик — код (@redflag_handler), см. services/medical.py
    }),
    "injury": ("Травма", {
        "fsm": {
            "states": ["anamnesis", "diagnosis", "treatment", "recovered"],
            "initial": "anamnesis",
            "transitions": [
                {"event": "diagnose", "source": "anamnesis", "dest": "diagnosis"},
                {"event": "treat",    "source": "diagnosis", "dest": "treatment"},
                {"event": "recover",  "source": "treatment", "dest": "recovered"},
            ],
        },
        "required": [
            {"category": "symptom", "scope": "episode"},
            {"category": "allergy", "scope": "patient"},
        ],
        "red_flags": [],
    }),
    # секции обзора систем (ROS) — детей-справочников пока не заводим
    "system": ("Система организма", {}),
    "document": ("Документ", {}),
    "analysis": ("Анализ", {}),   # статус один (результат) — FSM не нужен
}

# малый стартовый справочник: вид-концепт -> [(code, name), ...]
DICTIONARY = {
    "symptom": [
        ("headache", "Головная боль"), ("cough", "Кашель"),
        ("chest_pain", "Боль в груди"), ("dyspnea", "Одышка"),
        ("fever", "Лихорадка"), ("nausea", "Тошнота"),
        ("dizziness", "Головокружение"), ("rash", "Сыпь"),
        ("numbness", "Онемение"), ("weakness", "Слабость"),
    ],
    "medication": [
        ("aspirin", "Аспирин"), ("paracetamol", "Парацетамол"),
        ("ibuprofen", "Ибупрофен"), ("amoxicillin", "Амоксициллин"),
        ("omeprazole", "Омепразол"),
    ],
    "allergy": [
        ("penicillin", "Пенициллин"), ("pollen", "Пыльца"), ("nuts", "Орехи"),
    ],
    "system": [
        ("cardio", "Сердечно-сосудистая"), ("resp", "Дыхательная"),
        ("gi", "ЖКТ"), ("neuro", "Нервная"), ("skin", "Кожа"),
    ],
}


async def _get_category(db: AsyncSession, parent: uuid.UUID | None, code: str):
    q = select(tables.Category).where(tables.Category.code == code)
    q = q.where(tables.Category.category == parent) if parent is not None \
        else q.where(tables.Category.category.is_(None))
    return (await db.execute(q)).scalar_one_or_none()


async def medical_concepts(db: AsyncSession) -> dict[str, uuid.UUID]:
    """{code: Category.id} концептов — детей корня 'medical'.

    Единственная точка резолва кода в концепт (assess, ИИ-консумер, /me/concepts):
    привязка к корню исключает коллизию с тёзками-кодами из других деревьев."""
    root = await _get_category(db, None, "medical")
    if root is None:
        return {}
    rows = (await db.execute(select(tables.Category.code, tables.Category.id)
                             .where(tables.Category.category == root.id))).all()
    return dict(rows)


async def seed_medical(db: AsyncSession) -> dict[str, uuid.UUID]:
    """Создаёт (идемпотентно) медицинское дерево. Возвращает {code: category_id}."""
    root = await _get_category(db, None, "medical")
    if root is None:
        root = tables.Category(category=None, code="medical", name="Медицина")
        db.add(root)
        await db.flush()

    ids = {"medical": root.id}
    for code, (name, value) in CONCEPTS.items():
        cat = await _get_category(db, root.id, code)
        if cat is None:
            cat = tables.Category(category=root.id, code=code, name=name,
                                  value=value or None)
            db.add(cat)
            await db.flush()
        ids[code] = cat.id

    for kind, items in DICTIONARY.items():
        kind_id = ids[kind]
        for code, name in items:
            exists = (await db.execute(select(tables.Entity.id).where(
                tables.Entity.category == kind_id,
                tables.Entity.code == code))).scalar_one_or_none()
            if exists is None:
                db.add(tables.Entity(category=kind_id, code=code, name=name,
                                     table="category", objectid=root.id))
    await db.commit()
    return ids
