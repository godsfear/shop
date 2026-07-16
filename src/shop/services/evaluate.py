"""ИИ-клинический цикл эпизода (система поддержки, НЕ диагноз — решает врач):

1. WORKUP (topic 'episode.workup', авто после анамнеза): по собранному анамнезу
   ИИ рекомендует, какие анализы сдать для уточнения. Пишет Property(code='workup').
2. DIAGNOSIS (topic 'episode.evaluate', кнопка «Диагноз»): анамнез + ОРИГИНАЛЫ
   загруженных документов (мультимодально) -> ранжированный список предположений.
   Пишет Property(code='ddx') — одна активная оценка, повтор заменяет (версии).

Оба консумера живут в операционном контуре (identity не видят); возраст/пол
кладёт в payload вызывающий из своей персоны.
"""
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..logger import logger
from ..medical_seed import medical_concepts
from ..outbox import emit, outbox_handler
from ..settings import settings
from ..versioning import versioned_update
from .extract import _gemini_client
from .files import FileStore
from .. import tables

TOPIC_EVALUATE = 'episode.evaluate'
TOPIC_WORKUP = 'episode.workup'
DDX_CODE = 'ddx'
WORKUP_CODE = 'workup'
_INTERNAL_CODES = {DDX_CODE, WORKUP_CODE, 'state'}

_DDX_PROMPT = (
    'Ты — система поддержки принятия клинических решений. По анамнезу и '
    'приложенным документам (результаты анализов/обследований) предложи '
    'ранжированный список возможных состояний (differential diagnosis). Это '
    'ПРЕДПОЛОЖЕНИЯ для обсуждения с врачом, не диагноз. likelihood — субъективная '
    'вероятность 0..1, по убыванию. rationale — короткое обоснование со '
    'ссылкой на конкретные данные (в т.ч. значения из документов). urgent=true, если '
    'данные указывают на угрожающее состояние, требующее немедленной помощи.'
)
_DDX_SCHEMA = {
    'type': 'OBJECT',
    'properties': {
        'assessments': {
            'type': 'ARRAY',
            'items': {
                'type': 'OBJECT',
                'properties': {
                    'condition': {'type': 'STRING'},
                    'likelihood': {'type': 'NUMBER'},
                    'rationale': {'type': 'STRING'},
                },
                'required': ['condition', 'likelihood', 'rationale'],
            },
        },
        'urgent': {'type': 'BOOLEAN'},
        'note': {'type': 'STRING'},
    },
    'required': ['assessments', 'urgent'],
}

_WORKUP_PROMPT = (
    'Ты — система поддержки принятия клинических решений. По собранному анамнезу '
    'предложи, какие анализы и обследования стоит сдать пациенту, чтобы уточнить '
    'предположительный диагноз. Только обоснованное, по убыванию важности. test — '
    'название анализа/обследования; reason — зачем (что подтвердит/исключит).'
)


def _lang_note(lang: str) -> str:
    """Язык ответа задаётся при генерации (не переводом постфактум — решение
    владельца: переводы ИИ-текстов хуже прямой генерации)."""
    return (f' Все текстовые поля ответа (condition, rationale, test, reason, note) '
            f'пиши на языке с кодом ISO 639-1 "{lang}".')
_WORKUP_SCHEMA = {
    'type': 'OBJECT',
    'properties': {
        'tests': {
            'type': 'ARRAY',
            'items': {
                'type': 'OBJECT',
                'properties': {
                    'test': {'type': 'STRING'},
                    'reason': {'type': 'STRING'},
                },
                'required': ['test', 'reason'],
            },
        },
    },
    'required': ['tests'],
}


def request_evaluate(session: AsyncSession, episode_id: uuid.UUID,
                     pseudonym: uuid.UUID, age: int | None, sex: str | None,
                     lang: str = 'ru') -> None:
    """Диагноз в очередь — вызывать в транзакции (за воротами эпизода).
    lang — язык генерации ответа (консумер работает вне запроса)."""
    emit(session, TOPIC_EVALUATE, {'episode': str(episode_id), 'pseudonym': str(pseudonym),
                                   'age': age, 'sex': sex, 'lang': lang})


def request_workup(session: AsyncSession, episode_id: uuid.UUID,
                   pseudonym: uuid.UUID, lang: str = 'ru') -> None:
    """Рекомендацию анализов в очередь — авто после сбора анамнеза (интервью)."""
    emit(session, TOPIC_WORKUP, {'episode': str(episode_id), 'pseudonym': str(pseudonym),
                                 'lang': lang})


async def _bundle(session: AsyncSession, episode_id: uuid.UUID,
                  pseudonym: uuid.UUID) -> dict:
    """Анамнез: симптомы эпизода со слотами + анамнез жизни (коды концептов).
    Находки ИИ из документов (source=ai) НЕ включаем — оригиналы уходят
    мультимодально; служебные коды (ddx/workup/state) исключены."""
    cats = await medical_concepts(session)
    names = {v: k for k, v in cats.items()}

    def rows_to_list(rows):
        return [{'concept': names.get(p.category), 'code': p.code, **(p.value or {})}
                for p in rows if p.code not in _INTERNAL_CODES
                and (p.value or {}).get('source') != 'ai']

    ep = (await session.execute(select(tables.Property).where(
        tables.Property.table == 'entity',
        tables.Property.objectid == episode_id))).scalars().all()
    pat = (await session.execute(select(tables.Property).where(
        tables.Property.table == 'pseudonym',
        tables.Property.objectid == pseudonym))).scalars().all()
    return {'episode': rows_to_list(ep), 'patient': rows_to_list(pat)}


async def _episode_docs(session: AsyncSession, episode_id: uuid.UUID) -> list[tuple[bytes, str]]:
    """Оригиналы документов эпизода: (байты, mime) — для мультимодального диагноза."""
    rows = (await session.execute(select(tables.Data).where(
        tables.Data.table == 'entity', tables.Data.objectid == episode_id))).scalars().all()
    store = FileStore(session=session)
    out = []
    for d in rows:
        blob = await store.get(d.hash)
        if blob is not None:
            out.append((blob, d.media_type or 'application/pdf'))
    return out


def _with_identity(bundle: dict, payload: dict) -> dict:
    if payload.get('age') is not None:
        bundle['patient'].append({'concept': 'age', 'years': payload['age']})
    if payload.get('sex'):
        bundle['patient'].append({'concept': 'sex', 'value': payload['sex']})
    return bundle


async def _upsert(session: AsyncSession, episode_id: uuid.UUID, code: str, value: dict) -> None:
    existing = (await session.execute(select(tables.Property).where(
        tables.Property.table == 'entity', tables.Property.objectid == episode_id,
        tables.Property.code == code))).scalars().first()
    if existing is not None:
        await versioned_update(session, tables.Property, existing.id, {'value': value})
    else:
        session.add(tables.Property(table='entity', objectid=episode_id, code=code, value=value))


async def _gemini(prompt: str, schema: dict, bundle: dict,
                  docs: list[tuple[bytes, str]] | None = None) -> dict:
    from google.genai import types

    contents: list = [prompt, json.dumps(bundle, ensure_ascii=False)]
    for blob, mime in (docs or []):        # оригиналы документов — мультимодально
        contents.append(types.Part.from_bytes(data=blob, mime_type=mime))
    client = _gemini_client(settings.google_api_key)
    resp = await client.aio.models.generate_content(
        model=settings.gemini_model, contents=contents,
        config=types.GenerateContentConfig(response_mime_type='application/json',
                                            response_schema=schema))
    return json.loads(resp.text)


# ------------------------------------------------------------------ диагноз
@outbox_handler(TOPIC_EVALUATE)
async def _evaluate(session: AsyncSession, payload: dict) -> None:
    episode_id = uuid.UUID(payload['episode'])
    pseudonym = uuid.UUID(payload['pseudonym'])
    bundle = _with_identity(await _bundle(session, episode_id, pseudonym), payload)
    docs = await _episode_docs(session, episode_id)

    result = {'assessments': [{'condition': 'оценка недоступна (нет ключа ИИ)',
                               'likelihood': 0.0, 'rationale': f'документов: {len(docs)}'}],
              'urgent': False, 'note': 'заглушка без ИИ'}
    if settings.google_api_key:
        try:
            result = await _gemini(_DDX_PROMPT + _lang_note(payload.get('lang', 'ru')),
                                   _DDX_SCHEMA, bundle, docs)
            result['assessments'] = sorted(result.get('assessments', []),
                                           key=lambda a: -a.get('likelihood', 0))
        except Exception as e:  # noqa: BLE001 — сбой ИИ не должен ронять консумер
            logger.warning('evaluate: Gemini недоступен (%r) — заглушка', e)
    await _upsert(session, episode_id, DDX_CODE,
                  {**result, 'source': 'ai', 'model': settings.gemini_model,
                   'docs': len(docs)})
    # commit — за вызывающим (process_one / консумер шины)


# --------------------------------------------------------- рекомендация анализов
@outbox_handler(TOPIC_WORKUP)
async def _workup(session: AsyncSession, payload: dict) -> None:
    episode_id = uuid.UUID(payload['episode'])
    pseudonym = uuid.UUID(payload['pseudonym'])
    bundle = await _bundle(session, episode_id, pseudonym)

    result = {'tests': [], 'note': 'заглушка без ИИ'}
    if settings.google_api_key:
        try:
            result = await _gemini(_WORKUP_PROMPT + _lang_note(payload.get('lang', 'ru')),
                                   _WORKUP_SCHEMA, bundle)
        except Exception as e:  # noqa: BLE001
            logger.warning('workup: Gemini недоступен (%r) — заглушка', e)
    await _upsert(session, episode_id, WORKUP_CODE,
                  {**result, 'source': 'ai', 'model': settings.gemini_model})
