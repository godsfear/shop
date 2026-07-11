"""ИИ-консумер: документ/анализ (блоб) -> находки как Property на эпизоде.

outbox-топик 'data.extract', payload {hash, table, objectid, media_type}. Консумер
берёт блоб по хэшу (FileStore), гоняет мультимодальный экстрактор -> список находок
-> Property(source='ai') на носителе (эпизоде/псевдониме).

Экстрактор: Gemini по settings.google_api_key (мультимодальный разбор документа),
иначе — детерминированная ЗАГЛУШКА (без сети/ключа: тесты, dev). Любой сбой ИИ
откатывается на заглушку — outbox не должен падать из-за квоты/сети/ключа.
Сигнатура async extract(content, media_type) -> [{category, code, value}] — единый
шов, handler о провайдере не знает.
"""
import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..logger import logger
from ..outbox import emit, outbox_handler
from ..settings import settings
from .files import FileStore
from .. import tables

TOPIC_DATA_EXTRACT = 'data.extract'

_PROMPT = (
    'Ты — медицинский экстрактор. Извлеки из документа находки (симптомы, диагнозы, '
    'лекарства, результаты анализов) строго по схеме JSON. code — короткий слаг '
    'латиницей (напр. hemoglobin, chest_pain). kind — одно из: symptom, diagnosis, '
    'medication, analysis, other. Ничего не выдумывай: только то, что есть в документе.'
)
# схема Gemini (плоские STRING-поля — надёжнее вложенных для structured output)
_SCHEMA = {
    'type': 'OBJECT',
    'properties': {
        'findings': {
            'type': 'ARRAY',
            'items': {
                'type': 'OBJECT',
                'properties': {
                    'code': {'type': 'STRING'},
                    'kind': {'type': 'STRING'},
                    'text': {'type': 'STRING'},
                    'value': {'type': 'STRING'},
                    'unit': {'type': 'STRING'},
                },
                'required': ['code', 'kind', 'text'],
            },
        },
    },
    'required': ['findings'],
}


async def extract(content: bytes, media_type: str) -> list[dict]:
    """Документ -> находки {category, code, value}. Gemini при наличии ключа, иначе заглушка."""
    if settings.google_api_key:
        try:
            return await _extract_gemini(content, media_type)
        except Exception as e:  # noqa: BLE001 — сбой ИИ не должен ронять outbox-консумер
            logger.warning('extract: Gemini недоступен (%r) — откат на заглушку', e)
    return _stub(content, media_type)


async def _extract_gemini(content: bytes, media_type: str) -> list[dict]:
    from google import genai                       # ленивый импорт: без ключа не нужен
    from google.genai import types

    client = genai.Client(api_key=settings.google_api_key)
    resp = await client.aio.models.generate_content(
        model=settings.gemini_model,
        contents=[_PROMPT, types.Part.from_bytes(
            data=content, mime_type=media_type or 'application/pdf')],
        config=types.GenerateContentConfig(
            response_mime_type='application/json', response_schema=_SCHEMA))
    findings = json.loads(resp.text).get('findings', [])
    # category=None: концепт (symptom/... -> Category.id) маппится позже; kind несём в value.
    # ponytail: маппинг kind->category в handler, когда понадобится классификация в БД.
    return [{
        'category': None,
        'code': f['code'],
        'value': {'kind': f.get('kind'), 'text': f.get('text'),
                  'value': f.get('value'), 'unit': f.get('unit'),
                  'source': 'ai', 'confidence': 0.8},
    } for f in findings if f.get('code')]


def _stub(content: bytes, media_type: str) -> list[dict]:
    return [{
        'category': None,
        'code': 'summary',
        'value': {'text': f'stub extraction ({len(content)} bytes, {media_type or "?"})',
                  'source': 'ai', 'confidence': 0.0},
    }]


def request_extract(session: AsyncSession, blob_hash: str, table: str,
                    objectid: uuid.UUID, media_type: str = '') -> None:
    """Ставит документ в очередь на ИИ-разбор — вызывать в транзакции записи Data."""
    emit(session, TOPIC_DATA_EXTRACT, {
        'hash': blob_hash, 'table': table,
        'objectid': str(objectid), 'media_type': media_type,
    })


@outbox_handler(TOPIC_DATA_EXTRACT)
async def _extract_data(session: AsyncSession, payload: dict) -> None:
    content = await FileStore(session=session).get(payload['hash'])
    if content is None:
        return  # блоб не найден (удалён/не долит) — ретрай не поможет, пропускаем
    for f in await extract(content, payload.get('media_type', '')):
        session.add(tables.Property(
            table=payload['table'], objectid=uuid.UUID(payload['objectid']),
            category=f.get('category'), code=f['code'], value=f['value']))
    # commit — за process_one (вместе с пометкой события)
