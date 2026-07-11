"""Медицинский API: доступ к данным пациента через сессионный гибрид.

Псевдоним не фигурирует в путях/телах — он в Redis-сессии (см. MedAccessService).
Ответы — проекция MedPropertyOut (без objectid), псевдоним не утекает."""
import uuid
from typing import List

from fastapi import APIRouter, Depends, Form, Query, UploadFile, status

from ..models.medical import (SessionOpen, MedPropertyIn, MedPropertyOut,
                               EpisodeIn, EpisodeOut, Transition, DataOut)
from ..services.medaccess import MedAccessService

router = APIRouter(prefix='/me', tags=['medical'])


@router.post('/enroll', status_code=status.HTTP_204_NO_CONTENT)
async def enroll(svc: MedAccessService = Depends()):
    """Выпустить медицинский мост пациента (идемпотентно) — до первой сессии."""
    await svc.enroll()


@router.post('/session')
async def open_session(svc: MedAccessService = Depends(),
                       body: SessionOpen | None = None):
    """Открыть сессию доступа к медданным. Без тела — owner (свой мост по JWT);
    с link_id/key_id — делегированный доступ (врач/близкий)."""
    link_id = body.link_id if body else None
    key_id = body.key_id if body else None
    return {'expires_in': await svc.open_session(link_id, key_id)}


@router.get('/concepts')
async def concepts(svc: MedAccessService = Depends()):
    """{code: category_id} медицинских концептов — для форм создания."""
    return await svc.concepts()


@router.delete('/session', status_code=status.HTTP_204_NO_CONTENT)
async def close_session(svc: MedAccessService = Depends()):
    await svc.close_session()


# link_id/key_id заданы -> доступ по мосту (Слой B: врач/близкий, без сессии);
# не заданы -> из open-сессии (Слой A: owner). Псевдоним ни там, ни там не всплывает.
@router.get('/properties', response_model=List[MedPropertyOut])
async def my_properties(svc: MedAccessService = Depends(),
                        category: uuid.UUID | None = Query(None),
                        code: str | None = Query(None),
                        link_id: uuid.UUID | None = Query(None),
                        key_id: str | None = Query(None)):
    return await svc.properties(category, code, link_id, key_id)


@router.post('/properties', response_model=MedPropertyOut,
             status_code=status.HTTP_201_CREATED)
async def add_my_property(body: MedPropertyIn, svc: MedAccessService = Depends(),
                          link_id: uuid.UUID | None = Query(None),
                          key_id: str | None = Query(None)):
    return await svc.add_property(body, link_id, key_id)


# --- эпизоды (болезнь/травма) на псевдониме; доступ к {id} — за gate-проверкой ---
@router.get('/episodes', response_model=List[EpisodeOut])
async def my_episodes(svc: MedAccessService = Depends(),
                      link_id: uuid.UUID | None = Query(None),
                      key_id: str | None = Query(None)):
    return await svc.episodes(link_id, key_id)


@router.post('/episodes', response_model=EpisodeOut, status_code=status.HTTP_201_CREATED)
async def open_episode(body: EpisodeIn, svc: MedAccessService = Depends(),
                       link_id: uuid.UUID | None = Query(None),
                       key_id: str | None = Query(None)):
    return await svc.open_episode(body, link_id, key_id)


@router.get('/episodes/{episode_id}/properties', response_model=List[MedPropertyOut])
async def episode_properties(episode_id: uuid.UUID, svc: MedAccessService = Depends(),
                             category: uuid.UUID | None = Query(None),
                             code: str | None = Query(None),
                             link_id: uuid.UUID | None = Query(None),
                             key_id: str | None = Query(None)):
    return await svc.episode_properties(episode_id, category, code, link_id, key_id)


@router.post('/episodes/{episode_id}/properties', response_model=MedPropertyOut,
             status_code=status.HTTP_201_CREATED)
async def add_episode_property(episode_id: uuid.UUID, body: MedPropertyIn,
                               svc: MedAccessService = Depends(),
                               link_id: uuid.UUID | None = Query(None),
                               key_id: str | None = Query(None)):
    return await svc.add_episode_property(episode_id, body, link_id, key_id)


@router.get('/episodes/{episode_id}/state')
async def episode_state(episode_id: uuid.UUID, svc: MedAccessService = Depends(),
                        link_id: uuid.UUID | None = Query(None),
                        key_id: str | None = Query(None)):
    return await svc.episode_state(episode_id, link_id, key_id)


@router.post('/episodes/{episode_id}/transition')
async def episode_transition(episode_id: uuid.UUID, body: Transition,
                             svc: MedAccessService = Depends(),
                             link_id: uuid.UUID | None = Query(None),
                             key_id: str | None = Query(None)):
    return await svc.transition(episode_id, body.event, link_id, key_id)


@router.get('/episodes/{episode_id}/assess')
async def episode_assess(episode_id: uuid.UUID, svc: MedAccessService = Depends(),
                         link_id: uuid.UUID | None = Query(None),
                         key_id: str | None = Query(None)):
    return await svc.assess(episode_id, link_id, key_id)


# --- документы/анализы: загрузка (-> блоб + метаданные + ИИ-разбор), список ---
# episode_id (Query) -> прикрепить к эпизоду (за воротами), иначе к самому псевдониму.
@router.post('/documents', response_model=DataOut, status_code=status.HTTP_201_CREATED)
async def upload_document(file: UploadFile,
                          name: str = Form(...),
                          code: str = Form(...),
                          category: uuid.UUID | None = Form(None),
                          episode_id: uuid.UUID | None = Query(None),
                          svc: MedAccessService = Depends(),
                          link_id: uuid.UUID | None = Query(None),
                          key_id: str | None = Query(None)):
    content = await file.read()
    return await svc.upload_document(content, name, code, category,
                                     file.content_type or '', episode_id, link_id, key_id)


@router.get('/documents', response_model=List[DataOut])
async def my_documents(svc: MedAccessService = Depends(),
                       episode_id: uuid.UUID | None = Query(None),
                       link_id: uuid.UUID | None = Query(None),
                       key_id: str | None = Query(None)):
    return await svc.documents(episode_id, link_id, key_id)
