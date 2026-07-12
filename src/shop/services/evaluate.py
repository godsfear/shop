"""ИИ-оценка эпизода: все данные эпизода + профиль пациента -> ранжированный
список предположений (НЕ диагноз — система поддержки, решает врач).

outbox-топик 'episode.evaluate' (кнопка на эпизоде -> request_evaluate).
Консумер собирает симптомы со слотами, находки документов и анамнез жизни,
гоняет Gemini со structured output и пишет Property(code='ddx', source='ai')
на эпизод — одна активная оценка, повторный запуск заменяет (версии в истории).

Возраст/пол кладёт в payload вызывающий (владелец — из своей персоны);
консумер живёт в операционном контуре и identity-данных не видит.
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
from .. import tables

TOPIC_EVALUATE = 'episode.evaluate'
DDX_CODE = 'ddx'

_PROMPT = (
    'Ты — система поддержки принятия клинических решений. По данным эпизода и '
    'профилю пациента предложи ранжированный список возможных состояний '
    '(differential diagnosis). Это ПРЕДПОЛОЖЕНИЯ для обсуждения с врачом, не диагноз. '
    'likelihood — субъективная вероятность 0..1, по убыванию. rationale — короткое '
    'обоснование по-русски со ссылкой на конкретные данные. urgent=true, если данные '
    'указывают на угрожающее состояние, требующее немедленной помощи.'
)
_SCHEMA = {
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


def request_evaluate(session: AsyncSession, episode_id: uuid.UUID,
                     pseudonym: uuid.UUID, age: int | None, sex: str | None) -> None:
    """Ставит оценку в очередь — вызывать в транзакции (за воротами эпизода)."""
    emit(session, TOPIC_EVALUATE, {
        'episode': str(episode_id), 'pseudonym': str(pseudonym),
        'age': age, 'sex': sex,
    })


async def _bundle(session: AsyncSession, episode_id: uuid.UUID,
                  pseudonym: uuid.UUID) -> dict:
    """Все данные эпизода + анамнез жизни, с кодами концептов вместо id."""
    cats = await medical_concepts(session)
    names = {v: k for k, v in cats.items()}

    def rows_to_list(rows):
        return [{'concept': names.get(p.category), 'code': p.code, **(p.value or {})}
                for p in rows if p.code != DDX_CODE and p.code != 'state']

    ep = (await session.execute(select(tables.Property).where(
        tables.Property.table == 'entity',
        tables.Property.objectid == episode_id))).scalars().all()
    pat = (await session.execute(select(tables.Property).where(
        tables.Property.table == 'pseudonym',
        tables.Property.objectid == pseudonym))).scalars().all()
    return {'episode': rows_to_list(ep), 'patient': rows_to_list(pat)}


async def _evaluate_gemini(bundle: dict) -> dict:
    from google.genai import types

    client = _gemini_client(settings.google_api_key)
    resp = await client.aio.models.generate_content(
        model=settings.gemini_model,
        contents=[_PROMPT, json.dumps(bundle, ensure_ascii=False)],
        config=types.GenerateContentConfig(
            response_mime_type='application/json', response_schema=_SCHEMA))
    out = json.loads(resp.text)
    out['assessments'] = sorted(out.get('assessments', []),
                                key=lambda a: -a.get('likelihood', 0))
    return out


def _stub(bundle: dict) -> dict:
    return {'assessments': [{'condition': 'оценка недоступна (нет ключа ИИ)',
                             'likelihood': 0.0,
                             'rationale': f"собрано данных: эпизод {len(bundle['episode'])}, "
                                          f"карта {len(bundle['patient'])}"}],
            'urgent': False, 'note': 'заглушка без ИИ'}


@outbox_handler(TOPIC_EVALUATE)
async def _evaluate(session: AsyncSession, payload: dict) -> None:
    episode_id = uuid.UUID(payload['episode'])
    pseudonym = uuid.UUID(payload['pseudonym'])
    bundle = await _bundle(session, episode_id, pseudonym)
    if payload.get('age') is not None:
        bundle['patient'].append({'concept': 'age', 'years': payload['age']})
    if payload.get('sex'):
        bundle['patient'].append({'concept': 'sex', 'value': payload['sex']})

    result = _stub(bundle)
    if settings.google_api_key:
        try:
            result = await _evaluate_gemini(bundle)
        except Exception as e:  # noqa: BLE001 — сбой ИИ не должен ронять outbox
            logger.warning('evaluate: Gemini недоступен (%r) — заглушка', e)
    value = {**result, 'source': 'ai', 'model': settings.gemini_model}

    existing = (await session.execute(select(tables.Property).where(
        tables.Property.table == 'entity',
        tables.Property.objectid == episode_id,
        tables.Property.code == DDX_CODE))).scalars().first()
    if existing is not None:
        await versioned_update(session, tables.Property, existing.id, {'value': value})
    else:
        session.add(tables.Property(table='entity', objectid=episode_id,
                                    code=DDX_CODE, value=value))
    # commit — за process_one (вместе с пометкой события)
