"""Юр-документы: публичная отдача текста в языке запроса (нужна до регистрации,
поэтому без авторизации). Единый источник — БД (Entity под категорией 'legal'),
i18n — как везде: RU-база + Translation, фолбэк lang -> en -> база."""
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import db_helper
from ..services.translation import BASE_LANG, primary_language, resolve
from ..settings import settings
from .. import tables

router = APIRouter(prefix='/legal', tags=['legal'])


@router.get('/{code}')
async def legal_document(
        code: str,
        accept_language: Annotated[str | None, Header()] = None,
        session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
    """Текст документа: {version, title, body} на языке Accept-Language.
    version — действующая редакция (settings.terms_version), она же фиксируется
    на учётке при регистрации."""
    lang = primary_language(accept_language)
    ent = (await session.execute(
        select(tables.Entity)
        .join(tables.Category, tables.Category.id == tables.Entity.category)
        .where(tables.Category.code == 'legal',
               tables.Category.category.is_(None),   # top-level 'legal', не тёзка
               tables.Entity.code == code))).scalars().first()
    if ent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='doc_not_found')
    tr = {} if lang == BASE_LANG else await resolve(session, 'entity', [ent.id], lang)
    return {
        'version': settings.terms_version,
        'title': tr.get((ent.id, 'name'), ent.name),
        'body': tr.get((ent.id, 'description'), ent.description or ''),
    }
