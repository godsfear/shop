"""Сон: оценка качества за период — ИИ-консумер (по образцу нормы питания).

Оценка = Property(code='sleep_assessment') на псевдониме: пересчитывается один
раз при записи ночи (medaccess.add_sleep эмитит sleep.assess). Считается по
журналу последних ночей + данным карты (возраст/пол/рост/вес/хроника). Язык
ответа — язык пользователя (в payload). ИИ недоступен -> заглушка, консумер не
падает.
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

TOPIC_SLEEP = 'sleep.assess'
ASSESS_CODE = 'sleep_assessment'
_PERIOD = 14                     # сколько последних ночей отдаём ИИ

_ASSESS_PROMPT = (
    'Ты — врач-сомнолог. По журналу сна за последние ночи и данным пациента '
    'дай краткую оценку качества сна ЗА ПЕРИОД и 1–2 конкретные рекомендации. '
    'Отдельно оцени ТОЛЬКО текущую ночь из поля current: current_quality — '
    'одно слово, current_summary — 1–2 коротких предложения без выводов по '
    'предыдущим ночам. '
    'Смотри на продолжительность, эффективность, число и длительность '
    'пробуждений, ночной пульс, HRV, SpO2, утреннее самочувствие и их динамику. '
    'Учитывай возраст, пол и хронические состояния. quality — одно слово: '
    'хорошее, умеренное или плохое. summary — 2–3 предложения простым языком, '
    'с рекомендацией. Это ориентир, не диагноз.'
)
_ASSESS_SCHEMA = {
    'type': 'OBJECT',
    'properties': {
        'quality': {'type': 'STRING'},
        'summary': {'type': 'STRING'},
        'current_quality': {'type': 'STRING'},
        'current_summary': {'type': 'STRING'},
    },
    'required': ['quality', 'summary', 'current_quality', 'current_summary'],
}


def request_sleep_assess(session: AsyncSession, pseudonym: uuid.UUID,
                         age: int | None, sex: str | None,
                         residence: dict | None = None, lang: str = 'ru',
                         day: str | None = None) -> None:
    """Оценку сна за период в очередь — в транзакции записи ночи."""
    emit(session, TOPIC_SLEEP, {'pseudonym': str(pseudonym), 'age': age,
                                'sex': sex, 'residence': residence, 'lang': lang,
                                'day': day})


@outbox_handler(TOPIC_SLEEP)
async def _assess(session: AsyncSession, payload: dict) -> None:
    pseudonym = uuid.UUID(payload['pseudonym'])
    cats = await medical_concepts(session)

    nights = [p.value for p in (await session.execute(select(tables.Property).where(
        tables.Property.table == 'pseudonym',
        tables.Property.objectid == pseudonym,
        tables.Property.category == cats.get('sleep'))
        .order_by(tables.Property.begins.desc()).limit(_PERIOD))).scalars().all()]
    assessed_day = payload.get('day') or (
        str(nights[0].get('date')) if nights and nights[0].get('date') else None)
    current = next(
        (night for night in nights if str(night.get('date')) == assessed_day), None)

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
        'residence': payload.get('residence'),
        'height': await latest(cats.get('vital'), 'height'),
        'weight': await latest(cats.get('vital'), 'weight'),
        'chronic': list(chronic), 'nights': nights, 'current': current,
    }

    result = {
        'quality': '—', 'summary': 'оценка недоступна (нет ключа ИИ)',
        'current_quality': '—',
        'current_summary': 'оценка недоступна (нет ключа ИИ)',
    }
    if settings.google_api_key and nights:
        try:
            result = await _gemini(
                _ASSESS_PROMPT + _lang_note(payload.get('lang', 'ru')),
                _ASSESS_SCHEMA, bundle)
        except Exception as e:  # noqa: BLE001 — сбой ИИ не должен ронять консумер
            logger.warning('sleep: Gemini недоступен (%r) — заглушка', e)

    value = {**result, 'status': 'done', 'source': 'ai',
             'nights': len(nights), 'assessed_day': assessed_day,
             'model': settings.gemini_model}
    existing = (await session.execute(select(tables.Property).where(
        tables.Property.table == 'pseudonym',
        tables.Property.objectid == pseudonym,
        tables.Property.code == ASSESS_CODE))).scalars().first()
    if existing is not None:
        await versioned_update(session, tables.Property, existing.id, {'value': value})
    else:
        session.add(tables.Property(table='pseudonym', objectid=pseudonym,
                                    code=ASSESS_CODE, value=value))
    # commit — за вызывающим (process_one / консумер шины)
