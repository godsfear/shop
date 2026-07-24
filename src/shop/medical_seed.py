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
from .legal_seed import LEGAL_DOCS

# 11-слотовая схема разбора жалобы (OPQRST/SOCRATES + расширение).
# label — вопрос пациенту как есть: человеческим языком, без мед. жаргона;
# short — короткая подпись слота для развёрнутого анамнеза (эпизод, врач).
# associations — ПОСЛЕДНИЙ: выбор сопутствующих жалоб завершает разбор
# текущей и сразу ведёт к следующей (иначе «выбрал новую, а спрашивают
# опять про старую»).
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
    {"code": "impact",      "short": "влияние на жизнь",
     "label": "Мешает ли это спать, работать, заниматься обычными делами?"},
    {"code": "previous",    "short": "ранее случалось",
     "label": "Случалось ли такое раньше? Чем тогда закончилось?"},
    {"code": "associations", "short": "сопутствующие",
     "label": "Что ещё появилось одновременно с этим?"},
]

# слоты локализации/характера боли — неуместны для нелокализованных жалоб
_LOCALIZED_SLOTS = {"site", "character", "radiation"}
# нелокализованные (системные) жалобы: нет «где», «на что похоже», «отдаёт ли»
SYSTEMIC_SYMPTOMS = {"dizziness", "nausea", "fever", "chills", "weakness", "cough", "dyspnea",
                     "runny_nose", "diarrhea", "vomiting", "palpitations",
                     "heartburn", "insomnia"}

# элементы словаря, уместные только для одного пола (Person.sex: true = муж);
# dictionary() скрывает несоответствующие владельцу (кесарево у мужчины)
SEX_SPECIFIC = {
    "c_section": False,
    "hysterectomy": False,
    "pregnancy": False,
    "prostate_surgery": True,
}

# где уместен показатель: profile («Моя карта», постоянные данные) и/или
# diary (общий дневник состояния, замеры в моменте). Рост — только профиль;
# температура вне болезни не нужна — только дневник; неуказанные коды — везде.
VITAL_SCOPES = {
    "height": {"profile"},
    "weight": {"profile", "diary"},
    "blood_pressure": {"profile", "diary"},
    "pulse": {"profile", "diary"},
    "temperature": {"diary"},
    "glucose": {"diary"},          # замер в моменте по глюкометру
}

# Группа крови хранится как ОДИН профильный факт с этим стабильным code.
# Восемь элементов DICTIONARY["blood"] — допустимые значения этого факта,
# а не восемь независимо добавляемых свойств.
BLOOD_TYPE_CODE = "blood_type"


def symptom_slots(code: str, localized: bool | None = None) -> list[str]:
    """Слоты уточнения для жалобы. Локализованные (site/character/radiation)
    убраны у нелокализованных (системных) жалоб — «где болит» для бессонницы
    бессмысленно.

    Тип известной из справочника жалобы задан SYSTEMIC_SYMPTOMS. Для свободного
    текста тип указывает пациент (localized): False — общее состояние (убрать
    локализацию), True/None — локализованная (спрашиваем всё, как раньше)."""
    if code in _KNOWN_SYMPTOMS:
        systemic = code in SYSTEMIC_SYMPTOMS
    else:
        systemic = localized is False
    skip = _LOCALIZED_SLOTS if systemic else set()
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
    # документы «для пациента на руки»: их выдаёт врач (или грузит сам пациент),
    # ИИ их НЕ читает — см. _episode_docs/_PATIENT_ONLY в services/evaluate.py
    "referral": ("Направления", {}),
    "prescription": ("Рецепты", {}),
    # трекер питания: приёмы пищи (Property на псевдониме) + суточная норма;
    # оценка калорийности и норма — ИИ-консумеры (services/nutrition.py)
    "meal": ("Питание", {}),
    # трекер сна: журнал ночей (Property на псевдониме, generic /me/properties),
    # значение — набор показателей ночи; ИИ-консумеров пока нет
    "sleep": ("Сон", {}),
    # свободные комментарии пациента к эпизоду — доп. контекст для диагноза;
    # это обычные свойства эпизода, попадают в ИИ-бандл (_bundle)
    "note": ("Комментарии", {}),
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
        ("sore_throat", "Боль в горле"), ("runny_nose", "Насморк"),
        ("abdominal_pain", "Боль в животе"), ("back_pain", "Боль в спине"),
        ("joint_pain", "Боль в суставах"), ("diarrhea", "Диарея"),
        ("vomiting", "Рвота"), ("palpitations", "Учащённое сердцебиение"),
        ("heartburn", "Изжога"), ("insomnia", "Бессонница"),
    ],
    "medication": [
        ("aspirin", "Аспирин"), ("paracetamol", "Парацетамол"),
        ("ibuprofen", "Ибупрофен"), ("amoxicillin", "Амоксициллин"),
        ("omeprazole", "Омепразол"),
        ("metformin", "Метформин"), ("amlodipine", "Амлодипин"),
        ("losartan", "Лозартан"), ("atorvastatin", "Аторвастатин"),
        ("bisoprolol", "Бисопролол"), ("levothyroxine", "Левотироксин (L-тироксин)"),
        ("cetirizine", "Цетиризин"), ("azithromycin", "Азитромицин"),
        ("drotaverine", "Дротаверин (Но-шпа)"), ("insulin", "Инсулин"),
    ],
    "allergy": [
        ("penicillin", "Пенициллин"), ("pollen", "Пыльца"), ("nuts", "Орехи"),
        ("lactose", "Лактоза"), ("insect_sting", "Укусы насекомых"),
        ("dust_mites", "Домашняя пыль (клещи)"), ("animal_dander", "Шерсть животных"),
        ("eggs", "Яйца"), ("seafood", "Морепродукты"), ("citrus", "Цитрусовые"),
        ("sulfa", "Сульфаниламиды"), ("nsaids", "НПВС (аспирин, ибупрофен)"),
        ("contrast_iodine", "Йод / рентгеноконтраст"), ("latex", "Латекс"),
        ("mold", "Плесень"),
    ],
    "vital": [
        ("height", "Рост"), ("weight", "Вес"),
        ("blood_pressure", "Давление"), ("pulse", "Пульс"),
        ("temperature", "Температура"),   # дневник симптомов на эпизоде
        ("glucose", "Сахар крови"),       # глюкометр — дневник (диабет)
    ],
    "chronic": [
        ("hypertension", "Гипертония"), ("diabetes2", "Сахарный диабет 2 типа"),
        ("asthma", "Астма"), ("ihd", "ИБС"), ("gastritis", "Гастрит"),
        ("migraine", "Мигрень"),
        ("copd", "ХОБЛ"), ("hypothyroidism", "Гипотиреоз"),
        ("osteoarthritis", "Остеоартрит"), ("osteochondrosis", "Остеохондроз"),
        ("atrial_fibrillation", "Фибрилляция предсердий"),
        ("heart_failure", "Сердечная недостаточность"),
        ("ckd", "Хроническая болезнь почек"), ("gerd", "ГЭРБ (рефлюкс)"),
        ("depression", "Депрессия"),
    ],
    "heredity": [
        ("diabetes_family", "Диабет у родственников"),
        ("hypertension_family", "Гипертония у родственников"),
        ("cancer_family", "Онкология у родственников"),
        ("heart_family", "Инфаркт/инсульт у родственников"),
        ("asthma_family", "Астма/аллергии у родственников"),
        ("mental_family", "Психические заболевания у родственников"),
        ("thyroid_family", "Болезни щитовидной железы у родственников"),
        ("obesity_family", "Ожирение у родственников"),
        ("alzheimer_family", "Деменция/Альцгеймер у родственников"),
        ("glaucoma_family", "Глаукома у родственников"),
        ("thrombosis_family", "Тромбозы у родственников"),
        ("kidney_family", "Болезни почек у родственников"),
    ],
    "surgery": [
        ("appendectomy", "Аппендэктомия"), ("cholecystectomy", "Холецистэктомия"),
        ("c_section", "Кесарево сечение"), ("hospitalization", "Госпитализация"),
        ("hernia_repair", "Грыжесечение"), ("tonsillectomy", "Удаление миндалин"),
        ("joint_replacement", "Эндопротезирование сустава"),
        ("cataract_surgery", "Операция при катаракте"),
        ("thyroid_surgery", "Операция на щитовидной железе"),
        ("hysterectomy", "Удаление матки"),
        ("prostate_surgery", "Операция на предстательной железе"),
        ("varicose_surgery", "Операция на венах"),
        ("fracture_surgery", "Остеосинтез (операция при переломе)"),
        ("heart_surgery", "Операция на сердце / стентирование"),
    ],
    "social": [
        ("smoking", "Курение"), ("alcohol", "Алкоголь"),
        ("occupational", "Профессиональные вредности"), ("stress", "Хронический стресс"),
        ("sedentary", "Малоподвижная работа"),
        ("former_smoker", "Курение в прошлом"),
        ("vaping", "Вейп / электронные сигареты"),
        ("night_shifts", "Ночные смены"),
        ("heavy_physical", "Тяжёлый физический труд"),
        ("irregular_meals", "Нерегулярное питание"),
        ("sleep_deficit", "Хронический недосып"),
    ],
    "risk_factor": [
        ("obesity", "Избыточный вес"), ("inactivity", "Гиподинамия"),
        ("travel", "Недавние поездки"), ("infection_contact", "Контакт с инфекциями"),
        ("pregnancy", "Беременность"), ("tick_bite", "Укус клеща"),
        ("recent_surgery", "Недавняя операция"),
        ("immunodeficiency", "Сниженный иммунитет"),
        ("animal_contact", "Контакт с животными"),
        ("sun_exposure", "Избыточное солнце"),
    ],
    "vaccination": [
        ("flu", "Грипп"), ("covid", "COVID-19"), ("tetanus", "Столбняк (АДС-М)"),
        ("hepatitis_b", "Гепатит B"), ("measles", "Корь/краснуха/паротит (КПК)"),
        ("tick_encephalitis", "Клещевой энцефалит"),
        ("pneumococcus", "Пневмококк"), ("hpv", "ВПЧ"),
        ("chickenpox", "Ветряная оспа"), ("rabies", "Бешенство"),
    ],
    # группа крови — нотация языко-независима, en-переводы не нужны
    "blood": [
        ("o_pos", "O(I) Rh+"), ("o_neg", "O(I) Rh−"),
        ("a_pos", "A(II) Rh+"), ("a_neg", "A(II) Rh−"),
        ("b_pos", "B(III) Rh+"), ("b_neg", "B(III) Rh−"),
        ("ab_pos", "AB(IV) Rh+"), ("ab_neg", "AB(IV) Rh−"),
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

# коды известных жалоб — тип (локализуемость) определён; свободный текст вне
# набора получает тип от пациента (см. symptom_slots)
_KNOWN_SYMPTOMS = {c for c, _ in DICTIONARY["symptom"]}


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
    "referral": "Referrals", "prescription": "Prescriptions",
    "meal": "Nutrition", "sleep": "Sleep", "note": "Comments",
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
        "sore_throat": "Sore throat", "runny_nose": "Runny nose",
        "abdominal_pain": "Abdominal pain", "back_pain": "Back pain",
        "joint_pain": "Joint pain", "diarrhea": "Diarrhea",
        "vomiting": "Vomiting", "palpitations": "Palpitations",
        "heartburn": "Heartburn", "insomnia": "Insomnia",
    },
    "medication": {
        "aspirin": "Aspirin", "paracetamol": "Paracetamol", "ibuprofen": "Ibuprofen",
        "amoxicillin": "Amoxicillin", "omeprazole": "Omeprazole",
        "metformin": "Metformin", "amlodipine": "Amlodipine",
        "losartan": "Losartan", "atorvastatin": "Atorvastatin",
        "bisoprolol": "Bisoprolol", "levothyroxine": "Levothyroxine",
        "cetirizine": "Cetirizine", "azithromycin": "Azithromycin",
        "drotaverine": "Drotaverine", "insulin": "Insulin",
    },
    "allergy": {
        "penicillin": "Penicillin", "pollen": "Pollen", "nuts": "Nuts",
        "lactose": "Lactose", "insect_sting": "Insect stings",
        "dust_mites": "House dust mites", "animal_dander": "Animal dander",
        "eggs": "Eggs", "seafood": "Seafood", "citrus": "Citrus",
        "sulfa": "Sulfa drugs", "nsaids": "NSAIDs (aspirin, ibuprofen)",
        "contrast_iodine": "Iodine / contrast media", "latex": "Latex",
        "mold": "Mold",
    },
    "vital": {
        "height": "Height", "weight": "Weight",
        "blood_pressure": "Blood pressure", "pulse": "Pulse",
        "temperature": "Temperature", "glucose": "Blood sugar",
    },
    "chronic": {
        "hypertension": "Hypertension", "diabetes2": "Type 2 diabetes",
        "asthma": "Asthma", "ihd": "Coronary artery disease",
        "gastritis": "Gastritis", "migraine": "Migraine",
        "copd": "COPD", "hypothyroidism": "Hypothyroidism",
        "osteoarthritis": "Osteoarthritis", "osteochondrosis": "Spinal degeneration",
        "atrial_fibrillation": "Atrial fibrillation",
        "heart_failure": "Heart failure",
        "ckd": "Chronic kidney disease", "gerd": "GERD (reflux)",
        "depression": "Depression",
    },
    "heredity": {
        "diabetes_family": "Diabetes in the family",
        "hypertension_family": "Hypertension in the family",
        "cancer_family": "Cancer in the family",
        "heart_family": "Heart attack/stroke in the family",
        "asthma_family": "Asthma/allergies in the family",
        "mental_family": "Mental illness in the family",
        "thyroid_family": "Thyroid disease in the family",
        "obesity_family": "Obesity in the family",
        "alzheimer_family": "Dementia/Alzheimer's in the family",
        "glaucoma_family": "Glaucoma in the family",
        "thrombosis_family": "Blood clots in the family",
        "kidney_family": "Kidney disease in the family",
    },
    "surgery": {
        "appendectomy": "Appendectomy", "cholecystectomy": "Cholecystectomy",
        "c_section": "C-section", "hospitalization": "Hospitalization",
        "hernia_repair": "Hernia repair", "tonsillectomy": "Tonsillectomy",
        "joint_replacement": "Joint replacement",
        "cataract_surgery": "Cataract surgery",
        "thyroid_surgery": "Thyroid surgery",
        "hysterectomy": "Hysterectomy",
        "prostate_surgery": "Prostate surgery",
        "varicose_surgery": "Varicose vein surgery",
        "fracture_surgery": "Fracture fixation surgery",
        "heart_surgery": "Heart surgery / stenting",
    },
    "social": {
        "smoking": "Smoking", "alcohol": "Alcohol",
        "occupational": "Occupational hazards", "stress": "Chronic stress",
        "sedentary": "Sedentary work",
        "former_smoker": "Former smoker",
        "vaping": "Vaping / e-cigarettes",
        "night_shifts": "Night shifts",
        "heavy_physical": "Heavy physical labor",
        "irregular_meals": "Irregular meals",
        "sleep_deficit": "Chronic sleep deficit",
    },
    "risk_factor": {
        "obesity": "Excess weight", "inactivity": "Physical inactivity",
        "travel": "Recent travel", "infection_contact": "Contact with infections",
        "pregnancy": "Pregnancy", "tick_bite": "Tick bite",
        "recent_surgery": "Recent surgery",
        "immunodeficiency": "Weakened immunity",
        "animal_contact": "Contact with animals",
        "sun_exposure": "Excessive sun exposure",
    },
    "vaccination": {
        "flu": "Influenza", "covid": "COVID-19", "tetanus": "Tetanus",
        "hepatitis_b": "Hepatitis B", "measles": "Measles/rubella/mumps (MMR)",
        "tick_encephalitis": "Tick-borne encephalitis",
        "pneumococcus": "Pneumococcus", "hpv": "HPV",
        "chickenpox": "Chickenpox", "rabies": "Rabies",
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
    await _seed_legal(db)
    await db.commit()
    return ids


async def _seed_legal(db: AsyncSession) -> None:
    """Юр-документы (сид, истина): top-level категория 'legal' + Entity на
    документ; тело в description (RU-база), EN — в Translation. Отдельно от
    медицинского дерева, чтобы не попадать в /me/concepts."""
    en = (await db.execute(select(tables.Language.id).where(
        tables.Language.iso == 'en'))).scalar_one()
    cat = await _get_category(db, None, 'legal')
    if cat is None:
        cat = tables.Category(category=None, code='legal', name='Документы')
        db.add(cat)
        await db.flush()
    for code, doc in LEGAL_DOCS.items():
        ent = (await db.execute(select(tables.Entity).where(
            tables.Entity.category == cat.id,
            tables.Entity.code == code))).scalars().first()
        if ent is None:
            ent = tables.Entity(category=cat.id, code=code, name=doc['title_ru'],
                                description=doc['body_ru'],
                                table='category', objectid=cat.id)
            db.add(ent)
            await db.flush()
        else:                       # сид — истина: подхватываем правки текста
            ent.name, ent.description = doc['title_ru'], doc['body_ru']
        for field, content in (('name', doc['title_en']),
                               ('description', doc['body_en'])):
            row = (await db.execute(select(tables.Translation).where(
                tables.Translation.table == 'entity',
                tables.Translation.objectid == ent.id,
                tables.Translation.field == field,
                tables.Translation.language == en))).scalars().first()
            if row is None:
                db.add(tables.Translation(table='entity', objectid=ent.id,
                                          field=field, language=en, content=content))
            elif row.content != content:
                row.content = content


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
