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

# 11-слотовая схема разбора жалобы (OPQRST/SOCRATES + расширение).
# label — вопрос пациенту как есть: человеческим языком, без мед. жаргона;
# short — короткая подпись слота для развёрнутого анамнеза (эпизод, врач).
SYMPTOM_SCHEMA = [
    {"code": "onset",       "short": "начало",
     "label": "Когда это началось — и как: внезапно или постепенно?"},
    {"code": "site",        "short": "локализация",
     "label": "Где именно ощущается? Опишите место"},
    {"code": "character",   "short": "характер",
     "label": "На что похоже ощущение — ноет, жжёт, давит, колет?"},
    {"code": "severity",    "short": "интенсивность",
     "label": "Насколько сильно, по шкале от 0 до 10?"},
    {"code": "time",        "short": "динамика",
     "label": "Как меняется со временем — постоянно, приступами, лучше или хуже?"},
    {"code": "provocation", "short": "что провоцирует",
     "label": "Что это вызывает или усиливает?"},
    {"code": "palliation",  "short": "что облегчает",
     "label": "Что облегчает? Что уже пробовали?"},
    {"code": "radiation",   "short": "иррадиация",
     "label": "Отдаёт ли куда-то ещё — в руку, спину, ногу?"},
    {"code": "associations", "short": "сопутствующие",
     "label": "Что ещё появилось одновременно с этим?"},
    {"code": "impact",      "short": "влияние на жизнь",
     "label": "Мешает ли это спать, работать, заниматься обычными делами?"},
    {"code": "previous",    "short": "ранее случалось",
     "label": "Случалось ли такое раньше? Чем тогда закончилось?"},
]

# слоты локализации/характера боли — неуместны для нелокализованных жалоб
_LOCALIZED_SLOTS = {"site", "character", "radiation"}
# нелокализованные (системные) жалобы: нет «где», «на что похоже», «отдаёт ли»
SYSTEMIC_SYMPTOMS = {"dizziness", "nausea", "fever", "chills", "weakness", "cough", "dyspnea"}

# элементы словаря, уместные только для одного пола (Person.sex: true = муж);
# dictionary() скрывает несоответствующие владельцу (кесарево у мужчины)
SEX_SPECIFIC = {"c_section": False}


def symptom_slots(code: str) -> list[str]:
    """Слоты уточнения для жалобы. У нелокализованных (головокружение, тошнота…)
    убраны site/character/radiation; неизвестные (свой текст) — спрашиваем всё."""
    skip = _LOCALIZED_SLOTS if code in SYSTEMIC_SYMPTOMS else set()
    return [s["code"] for s in SYMPTOM_SCHEMA if s["code"] not in skip]

# подписи состояний/событий эпизода — фронт получает их из GET /me/meta:
# единый источник подписей — сид/БД, во фронте доменных текстов нет
_EPISODE_STATE_LABELS = {
    "anamnesis": "анамнез", "diagnosis": "диагноз", "treatment": "лечение",
    "remission": "ремиссия", "recovered": "выздоровление",
}
_EPISODE_EVENT_LABELS = {
    "diagnose": "Поставить диагноз", "treat": "Начать лечение",
    "recover": "Выздоровление", "remit": "Ремиссия", "relapse": "Рецидив",
}

# концепты: code -> (name, value-конфиг); name — подпись для UI (секции, чипы)
CONCEPTS = {
    "symptom":     ("Симптомы", {"schema": SYMPTOM_SCHEMA}),
    "medication":  ("Лекарства", {}),
    "allergy":     ("Аллергии", {}),
    "heredity":    ("Наследственность", {}),
    "risk_factor": ("Факторы риска", {}),
    # профиль здоровья владельца (scope=patient, экран «Моя карта»)
    "vital":       ("Показатели", {}),           # рост/вес/давление — история темпоральностью
    "chronic":     ("Хронические состояния", {}),
    "blood":       ("Группа крови", {}),
    "vaccination": ("Прививки", {}),
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
            "state_labels": _EPISODE_STATE_LABELS,
            "event_labels": _EPISODE_EVENT_LABELS,
        },
        # секции полноты: {category-код концепта, scope: episode|patient}
        "required": [
            {"category": "symptom",    "scope": "episode"},
            {"category": "medication", "scope": "patient"},
            {"category": "allergy",    "scope": "patient"},
            {"category": "chronic",    "scope": "patient"},
            {"category": "heredity",   "scope": "patient"},
            {"category": "surgery",    "scope": "patient"},
            {"category": "social",     "scope": "patient"},
        ],
        "red_flags": ["acs"],   # обработчик — код (@redflag_handler), см. services/medical.py
        "red_flag_labels": {"acs": "острый коронарный синдром"},
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
            # общие подписи эпизода: лишние ключи (remission) безвредны — meta мержит
            "state_labels": _EPISODE_STATE_LABELS,
            "event_labels": _EPISODE_EVENT_LABELS,
        },
        "required": [
            {"category": "symptom", "scope": "episode"},
            {"category": "allergy", "scope": "patient"},
        ],
        "red_flags": [],
    }),
    "surgery":  ("Операции/госпитализации", {}),
    "social":   ("Социальный анамнез", {}),
    "system": ("Система организма", {}),
    "document": ("Документ", {}),
    "analysis": ("Анализ", {}),   # статус один (результат) — FSM не нужен
    # процесс сбора анамнеза (anamnez.md): интервью — Entity на эпизоде со своей FSM;
    # очередь симптомов/прогресс — Property(code='progress'), см. services/interview.py
    "interview": ("Опрос (анамнез)", {
        "fsm": {
            "states": ["complaint", "symptom", "ros", "history",
                       "completeness", "summary", "confirmed", "emergency"],
            "initial": "complaint",
            "transitions": [
                {"event": "begin_symptoms",  "source": "complaint",    "dest": "symptom"},
                {"event": "to_ros",          "source": "symptom",      "dest": "ros"},
                {"event": "back_to_symptoms", "source": "ros",         "dest": "symptom"},
                {"event": "to_history",      "source": "ros",          "dest": "history"},
                {"event": "to_completeness", "source": "history",      "dest": "completeness"},
                {"event": "to_summary",      "source": "completeness", "dest": "summary"},
                # возврат «да, ещё...»: ROS/анамнез уже пройдены — из цикла сразу к резюме
                {"event": "to_summary",      "source": "symptom",      "dest": "summary"},
                {"event": "more_symptoms",   "source": "summary",      "dest": "symptom"},
                {"event": "confirm",         "source": "summary",      "dest": "confirmed"},
                # красный флаг прерывает опрос; resume — после оказания помощи
                {"event": "red_flag",        "source": "symptom",      "dest": "emergency"},
                {"event": "resume",          "source": "emergency",    "dest": "symptom"},
            ],
            "state_labels": {
                "complaint": "жалоба", "symptom": "симптомы", "ros": "обзор систем",
                "history": "анамнез жизни", "completeness": "полнота",
                "summary": "резюме", "confirmed": "подтверждено", "emergency": "экстренно",
            },
        },
    }),
}

# малый стартовый справочник: вид-концепт -> [(code, name), ...]
DICTIONARY = {
    "symptom": [
        ("headache", "Головная боль"), ("cough", "Кашель"),
        ("chest_pain", "Боль в груди"), ("dyspnea", "Одышка"),
        # «лихорадка» — жаргон, пациент читает неоднозначно (озноб?)
        ("fever", "Повышенная температура (жар)"), ("chills", "Озноб"),
        ("nausea", "Тошнота"),
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
        ("lactose", "Лактоза"), ("insect_sting", "Укусы насекомых"),
    ],
    "vital": [
        ("height", "Рост"), ("weight", "Вес"),
        ("blood_pressure", "Давление"), ("pulse", "Пульс"),
    ],
    "chronic": [
        ("hypertension", "Гипертония"), ("diabetes2", "Сахарный диабет 2 типа"),
        ("asthma", "Астма"), ("ihd", "ИБС"), ("gastritis", "Гастрит"),
        ("migraine", "Мигрень"),
    ],
    "heredity": [
        ("diabetes_family", "Диабет у родственников"),
        ("hypertension_family", "Гипертония у родственников"),
        ("cancer_family", "Онкология у родственников"),
        ("heart_family", "Инфаркт/инсульт у родственников"),
    ],
    "surgery": [
        ("appendectomy", "Аппендэктомия"), ("cholecystectomy", "Холецистэктомия"),
        ("c_section", "Кесарево сечение"), ("hospitalization", "Госпитализация"),
    ],
    "social": [
        ("smoking", "Курение"), ("alcohol", "Алкоголь"),
        ("occupational", "Профессиональные вредности"), ("stress", "Хронический стресс"),
        ("sedentary", "Малоподвижная работа"),
    ],
    "risk_factor": [
        ("obesity", "Избыточный вес"), ("inactivity", "Гиподинамия"),
        ("travel", "Недавние поездки"), ("infection_contact", "Контакт с инфекциями"),
    ],
    # обзор систем (ROS) — все 9 систем эталона, порядок = порядок обхода
    "system": [
        ("neuro", "Нервная"), ("cardio", "Сердечно-сосудистая"),
        ("resp", "Дыхательная"), ("gi", "ЖКТ"),
        ("gu", "Мочеполовая"), ("endo", "Эндокринная"),
        ("msk", "Опорно-двигательная"), ("skin", "Кожа"),
        ("psych", "Психическая"),
    ],
}


# ------------------------------------------------------------------ en-переводы
# Английские подписи справочного дерева (Translation, язык en).
# Базовые поля (name, метки в value) — ru; фолбэк: lang -> en -> базовое.
CONCEPTS_EN = {
    "symptom": "Symptoms", "medication": "Medications", "allergy": "Allergies",
    "heredity": "Family history", "risk_factor": "Risk factors",
    "vital": "Vitals", "chronic": "Chronic conditions", "blood": "Blood type",
    "vaccination": "Vaccinations", "illness": "Illness", "injury": "Injury",
    "surgery": "Surgeries/hospitalizations", "social": "Social history",
    "system": "Body system", "document": "Document", "analysis": "Test",
    "interview": "Interview (anamnesis)",
}
SLOTS_EN = {
    "onset":       "When did it start — and how: suddenly or gradually?",
    "site":        "Where exactly do you feel it? Describe the spot",
    "character":   "What does it feel like — aching, burning, pressing, stabbing?",
    "severity":    "How bad is it, on a scale from 0 to 10?",
    "time":        "How does it change over time — constant, in attacks, better or worse?",
    "provocation": "What brings it on or makes it worse?",
    "palliation":  "What relieves it? What have you already tried?",
    "radiation":   "Does it spread anywhere — to an arm, back, leg?",
    "associations": "What else appeared along with it?",
    "impact":      "Does it interfere with sleep, work, daily activities?",
    "previous":    "Has this happened before? How did it end then?",
}
SLOT_SHORT_EN = {
    "onset": "onset", "site": "location", "character": "character",
    "severity": "severity", "time": "time course", "provocation": "triggers",
    "palliation": "relief", "radiation": "radiation",
    "associations": "associated", "impact": "impact on life",
    "previous": "previous episodes",
}
EPISODE_STATES_EN = {"anamnesis": "history taking", "diagnosis": "diagnosis",
                     "treatment": "treatment", "remission": "remission",
                     "recovered": "recovered"}
EPISODE_EVENTS_EN = {"diagnose": "Make a diagnosis", "treat": "Start treatment",
                     "recover": "Recovery", "remit": "Remission", "relapse": "Relapse"}
INTERVIEW_STATES_EN = {"complaint": "chief complaint", "symptom": "symptoms",
                       "ros": "review of systems", "history": "life history",
                       "completeness": "completeness", "summary": "summary",
                       "confirmed": "confirmed", "emergency": "emergency"}
RED_FLAGS_EN = {"acs": "acute coronary syndrome"}
DICTIONARY_EN = {
    "symptom": {
        "headache": "Headache", "cough": "Cough", "chest_pain": "Chest pain",
        "dyspnea": "Shortness of breath", "fever": "Fever (high temperature)",
        "chills": "Chills", "nausea": "Nausea",
        "dizziness": "Dizziness", "rash": "Rash", "numbness": "Numbness",
        "weakness": "Weakness",
    },
    "medication": {
        "aspirin": "Aspirin", "paracetamol": "Paracetamol", "ibuprofen": "Ibuprofen",
        "amoxicillin": "Amoxicillin", "omeprazole": "Omeprazole",
    },
    "allergy": {
        "penicillin": "Penicillin", "pollen": "Pollen", "nuts": "Nuts",
        "lactose": "Lactose", "insect_sting": "Insect stings",
    },
    "vital": {
        "height": "Height", "weight": "Weight",
        "blood_pressure": "Blood pressure", "pulse": "Pulse",
    },
    "chronic": {
        "hypertension": "Hypertension", "diabetes2": "Type 2 diabetes",
        "asthma": "Asthma", "ihd": "Coronary artery disease",
        "gastritis": "Gastritis", "migraine": "Migraine",
    },
    "heredity": {
        "diabetes_family": "Diabetes in the family",
        "hypertension_family": "Hypertension in the family",
        "cancer_family": "Cancer in the family",
        "heart_family": "Heart attack/stroke in the family",
    },
    "surgery": {
        "appendectomy": "Appendectomy", "cholecystectomy": "Cholecystectomy",
        "c_section": "C-section", "hospitalization": "Hospitalization",
    },
    "social": {
        "smoking": "Smoking", "alcohol": "Alcohol",
        "occupational": "Occupational hazards", "stress": "Chronic stress",
        "sedentary": "Sedentary work",
    },
    "risk_factor": {
        "obesity": "Excess weight", "inactivity": "Physical inactivity",
        "travel": "Recent travel", "infection_contact": "Contact with infections",
    },
    "system": {
        "neuro": "Nervous", "cardio": "Cardiovascular", "resp": "Respiratory",
        "gi": "Gastrointestinal", "gu": "Genitourinary", "endo": "Endocrine",
        "msk": "Musculoskeletal", "skin": "Skin", "psych": "Psychiatric",
    },
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
        elif (cat.value or None) != (value or None) or cat.name != name:
            # конфиг или подпись концепта изменились — обновить:
            # сид — источник правды для справочного дерева
            cat.value = value or None
            cat.name = name
            await db.flush()
        ids[code] = cat.id

    entity_ids: dict[tuple[str, str], uuid.UUID] = {}
    for kind, items in DICTIONARY.items():
        kind_id = ids[kind]
        for code, name in items:
            row = (await db.execute(select(tables.Entity).where(
                tables.Entity.category == kind_id,
                tables.Entity.code == code))).scalars().first()
            if row is None:
                row = tables.Entity(category=kind_id, code=code, name=name,
                                    table="category", objectid=root.id)
                db.add(row)
                await db.flush()
            elif row.name != name:
                row.name = name     # подпись изменилась — сид истина и для словаря
            entity_ids[(kind, code)] = row.id

    await _seed_translations(db, ids, entity_ids)
    await db.commit()
    return ids


async def _seed_translations(db: AsyncSession, ids: dict, entity_ids: dict) -> None:
    """Языки ru/en + английские переводы дерева (идемпотентно; сид — истина)."""
    langs = {}
    for iso, name in (("ru", "Русский"), ("en", "English")):
        row = (await db.execute(select(tables.Language).where(
            tables.Language.iso == iso))).scalars().first()
        if row is None:
            row = tables.Language(code=iso, iso=iso, name=name)
            db.add(row)
            await db.flush()
        langs[iso] = row.id
    en = langs["en"]

    async def tr(table: str, objectid: uuid.UUID, field: str, content: str) -> None:
        row = (await db.execute(select(tables.Translation).where(
            tables.Translation.table == table,
            tables.Translation.objectid == objectid,
            tables.Translation.field == field,
            tables.Translation.language == en))).scalars().first()
        if row is None:
            db.add(tables.Translation(table=table, objectid=objectid,
                                      field=field, language=en, content=content))
        elif row.content != content:
            row.content = content

    for code, name_en in CONCEPTS_EN.items():
        await tr("category", ids[code], "name", name_en)
    for code, text_en in SLOTS_EN.items():
        await tr("category", ids["symptom"], f"slot.{code}", text_en)
    for code, text_en in SLOT_SHORT_EN.items():
        await tr("category", ids["symptom"], f"slot_short.{code}", text_en)
    # метки эпизодных FSM — на каждом виде эпизода (meta читает по-категорийно)
    for kind in ("illness", "injury"):
        for code, label in EPISODE_STATES_EN.items():
            await tr("category", ids[kind], f"state.{code}", label)
        for code, label in EPISODE_EVENTS_EN.items():
            await tr("category", ids[kind], f"event.{code}", label)
    for code, label in INTERVIEW_STATES_EN.items():
        await tr("category", ids["interview"], f"state.{code}", label)
    for code, label in RED_FLAGS_EN.items():
        await tr("category", ids["illness"], f"red_flag.{code}", label)
    for kind, items in DICTIONARY_EN.items():
        for code, name_en in items.items():
            await tr("entity", entity_ids[(kind, code)], "name", name_en)
