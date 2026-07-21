"""Админ-инструменты. Пока — read-only статистика «сколько в базе чего».

Гейт — require_admin (роль admin в JWT). Первый админ назначается вне API:
python -m shop.grant_admin <email> (см. grant_admin.py) — API set_roles сам
требует админа, иначе курица-яйцо.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import db_helper
from ..services.auth import require_admin
from .. import tables

router = APIRouter(prefix='/admin', tags=['admin'],
                   dependencies=[Depends(require_admin)])

# что считаем: имя в ответе -> таблица. Порядок = порядок вывода.
_COUNTS: dict[str, type] = {
    'users': tables.User,
    'persons': tables.Person,
    'pseudonyms': tables.Pseudonym,
    'pseudonym_pool_free': tables.PseudonymPool,
    'properties': tables.Property,
    'documents': tables.Document,
    'blobs': tables.Blob,
    'consents': tables.Consent,
    'keys': tables.Key,
    'entities': tables.Entity,
    'translations': tables.Translation,
}


async def _count(session: AsyncSession, model: type) -> int:
    q = select(func.count()).select_from(model)
    # версионируемые (Base): считаем только живые строки — не копии-версии
    # (version_of != NULL) и не погашенные (ends != NULL)
    if hasattr(model, 'version_of'):
        q = q.where(model.version_of.is_(None), model.ends.is_(None))
    return (await session.execute(q)).scalar_one()


@router.get('/stats')
async def stats(session: AsyncSession = Depends(db_helper.scoped_session_dependency)
                ) -> dict[str, int]:
    out = {name: await _count(session, model) for name, model in _COUNTS.items()}
    out['users_confirmed'] = (await session.execute(
        select(func.count()).select_from(tables.User)
        .where(tables.User.version_of.is_(None), tables.User.ends.is_(None),
               tables.User.confirmed.is_(True)))).scalar_one()
    return out
