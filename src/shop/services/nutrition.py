"""Питание: оценка приёмов пищи (фото/описание) и суточная норма — ИИ-консумеры.

- приём пищи = Property(category=meal) на псевдониме: API создаёт запись со
  status='estimating', консумер дозаполняет цифрами (ккал + БЖУ по позициям);
- фото НЕ хранится (решение владельца): блоб транзитный, удаляется после
  оценки (delete_unreferenced — дедуп не даёт снести чужой документ);
- норма = Property(code='nutrition_norm') на псевдониме: пересчитывается
  лениво, когда запрошенный день новее даты нормы (см. medaccess.nutrition);
  считается по данным карты — рост/вес/возраст/пол/хроника, цель — поддержание.

Язык текстов ответа — язык пользователя (в payload), не перевод постфактум.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..logger import logger
from ..medical_seed import medical_concepts
from ..outbox import emit, outbox_handler
from ..settings import settings
from ..versioning import versioned_update
from .. import tables
from .evaluate import _gemini, _lang_note
from .files import FileStore

TOPIC_MEAL = 'meal.estimate'
TOPIC_NORM = 'nutrition.norm'
NORM_CODE = 'nutrition_norm'

_MEAL_PROMPT = (
    'Ты — нутрициолог. По фото и/или описанию приёма пищи оцени состав: '
    'каждая позиция с калорийностью (kcal) и БЖУ в граммах (protein, fat, '
    'carbs). Оценивай реалистичные порции; если порция не видна — среднюю. '
    'name — короткое название блюда; note — одно замечание, если что-то '
    'важно (например, «порция оценена приблизительно»).'
)
_MEAL_SCHEMA = {
    'type': 'OBJECT',
    'properties': {
        'items': {
            'type': 'ARRAY',
            'items': {
                'type': 'OBJECT',
                'properties': {
                    'name': {'type': 'STRING'},
                    'kcal': {'type': 'NUMBER'},
                    'protein': {'type': 'NUMBER'},
                    'fat': {'type': 'NUMBER'},
                    'carbs': {'type': 'NUMBER'},
                },
                'required': ['name', 'kcal', 'protein', 'fat', 'carbs'],
            },
        },
        'note': {'type': 'STRING'},
    },
    'required': ['items'],
}

_NORM_PROMPT = (
    'Ты — нутрициолог. По данным пациента рассчитай СУТОЧНУЮ норму '
    'ПОДДЕРЖАНИЯ веса: калории (kcal) и БЖУ в граммах (protein_g, fat_g, '
    'carbs_g). Учитывай возраст, пол, рост, вес и хронические состояния '
    '(например, при диабете — замечание про углеводы). Активность считай '
    'лёгкой, если данных нет. note — короткое пояснение расчёта. '
    'Это ориентир для здорового питания, не лечебная диета.'
)
_NORM_SCHEMA = {
    'type': 'OBJECT',
    'properties': {
        'kcal': {'type': 'NUMBER'},
        'protein_g': {'type': 'NUMBER'},
        'fat_g': {'type': 'NUMBER'},
        'carbs_g': {'type': 'NUMBER'},
        'note': {'type': 'STRING'},
    },
    'required': ['kcal', 'protein_g', 'fat_g', 'carbs_g'],
}


def request_meal_estimate(session: AsyncSession, property_id: uuid.UUID,
                          blob_hash: str | None, media_type: str | None,
                          desc: str, lang: str = 'ru') -> None:
    """Оценку приёма пищи в очередь — в транзакции создания записи."""
    emit(session, TOPIC_MEAL, {'property': str(property_id), 'hash': blob_hash,
                               'media_type': media_type, 'desc': desc, 'lang': lang})


def request_norm(session: AsyncSession, pseudonym: uuid.UUID, day: str,
                 age: int | None, sex: str | None, lang: str = 'ru') -> None:
    """Пересчёт суточной нормы в очередь (лениво, по первому заходу за день)."""
    emit(session, TOPIC_NORM, {'pseudonym': str(pseudonym), 'day': day,
                               'age': age, 'sex': sex, 'lang': lang})


@outbox_handler(TOPIC_MEAL)
async def _estimate(session: AsyncSession, payload: dict) -> None:
    prop = await session.get(tables.Property, uuid.UUID(payload['property']))
    if prop is None:                       # запись удалили до оценки — нечего делать
        return
    store = FileStore(session=session)
    photo = await store.get(payload['hash']) if payload.get('hash') else None

    result = {'items': [], 'note': 'оценка недоступна (нет ключа ИИ)'}
    if settings.google_api_key:
        try:
            docs = [(photo, payload.get('media_type') or 'image/jpeg')] if photo else None
            result = await _gemini(
                _MEAL_PROMPT + _lang_note(payload.get('lang', 'ru')),
                _MEAL_SCHEMA, {'desc': payload.get('desc', '')}, docs)
        except Exception as e:  # noqa: BLE001 — сбой ИИ не должен ронять консумер
            logger.warning('meal: Gemini недоступен (%r) — заглушка', e)
    items = result.get('items') or []
    totals = {k: round(sum(float(i.get(k) or 0) for i in items), 1)
              for k in ('kcal', 'protein', 'fat', 'carbs')}
    await versioned_update(session, tables.Property, prop.id, {'value': {
        **prop.value, 'status': 'done', 'items': items, 'totals': totals,
        'note': result.get('note'), 'model': settings.gemini_model}})
    if payload.get('hash'):                # фото транзитное — не храним (решение владельца)
        await store.delete_unreferenced(payload['hash'])
    # commit — за вызывающим (process_one / консумер шины)


@outbox_handler(TOPIC_NORM)
async def _norm(session: AsyncSession, payload: dict) -> None:
    pseudonym = uuid.UUID(payload['pseudonym'])
    cats = await medical_concepts(session)

    async def latest(category: uuid.UUID | None, code: str) -> dict | None:
        if category is None:
            return None
        row = (await session.execute(select(tables.Property).where(
            tables.Property.table == 'pseudonym',
            tables.Property.objectid == pseudonym,
            tables.Property.category == category,
            tables.Property.code == code)
            .order_by(tables.Property.begins.desc()))).scalars().first()
        return row.value if row else None

    chronic = (await session.execute(select(tables.Property.code).where(
        tables.Property.table == 'pseudonym',
        tables.Property.objectid == pseudonym,
        tables.Property.category == cats.get('chronic')))).scalars().all()
    bundle = {
        'age': payload.get('age'), 'sex': payload.get('sex'),
        'height': await latest(cats.get('vital'), 'height'),
        'weight': await latest(cats.get('vital'), 'weight'),
        'chronic': list(chronic),
    }

    result = {'kcal': 2000, 'protein_g': 75, 'fat_g': 70, 'carbs_g': 250,
              'note': 'заглушка без ИИ'}
    if settings.google_api_key:
        try:
            result = await _gemini(
                _NORM_PROMPT + _lang_note(payload.get('lang', 'ru')),
                _NORM_SCHEMA, bundle)
        except Exception as e:  # noqa: BLE001
            logger.warning('norm: Gemini недоступен (%r) — заглушка', e)

    value = {**result, 'status': 'done', 'date': payload['day'],
             'source': 'ai', 'model': settings.gemini_model}
    existing = (await session.execute(select(tables.Property).where(
        tables.Property.table == 'pseudonym',
        tables.Property.objectid == pseudonym,
        tables.Property.code == NORM_CODE))).scalars().first()
    if existing is not None:
        await versioned_update(session, tables.Property, existing.id, {'value': value})
    else:
        session.add(tables.Property(table='pseudonym', objectid=pseudonym,
                                    code=NORM_CODE, value=value))
