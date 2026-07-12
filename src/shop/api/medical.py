"""Медицинский API: доступ к данным пациента через сессионный гибрид.

Псевдоним не фигурирует в путях/телах — он в Redis-сессии (см. MedAccessService).
Ответы — проекция MedPropertyOut (без objectid), псевдоним не утекает."""
import uuid
from typing import List

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status

from ..models.medical import (SessionOpen, MedPropertyIn, MedPropertyOut,
                               EpisodeIn, EpisodeOut, EpisodeRename, Transition, DataOut)
from ..services.medaccess import MedAccessService

router = APIRouter(prefix='/me', tags=['medical'])


@router.post('/enroll', status_code=status.HTTP_204_NO_CONTENT)
async def enroll(svc: MedAccessService = Depends()):
    """Выпустить медицинский мост пациента (идемпотентно) — до первой сессии."""
    await svc.enroll()


@router.post('/session')
async def open_session(svc: MedAccessService = Depends(),
                       body: SessionOpen | None = None):
    """Открыть owner-сессию (свой мост по JWT). Делегированный доступ (Слой B)
    сессию НЕ использует — link_id/key_id передаются в каждом запросе."""
    if body is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='делегированный доступ не использует сессию — '
                                   'передавайте link_id/key_id в каждом запросе')
    return {'expires_in': await svc.open_session()}


@router.get('/grants')
async def my_grants(svc: MedAccessService = Depends()):
    """Чужие медкарты, доступные мне по одобренным согласиям (Слой B):
    [{link_id, key_id}] — передавать в запросах /me/* как query-параметры."""
    return await svc.grants()


@router.get('/concepts')
async def concepts(svc: MedAccessService = Depends()):
    """{code: category_id} медицинских концептов — для форм создания."""
    return await svc.concepts()


@router.get('/dictionary/{concept}')
async def dictionary(concept: str, svc: MedAccessService = Depends()):
    """Справочник элементов концепта: [{code, name}] — чипы выбора в интервью."""
    return await svc.dictionary(concept)


@router.delete('/session', status_code=status.HTTP_204_NO_CONTENT)
async def close_session(svc: MedAccessService = Depends()):
    await svc.close_session()


# link_id/key_id заданы -> доступ по мосту (Слой B: врач/близкий, без сессии);
# не заданы -> из open-сессии (Слой A: owner). Псевдоним ни там, ни там не всплывает.
@router.get('/properties', response_model=List[MedPropertyOut])
async def my_properties(svc: MedAccessService = Depends(),
                        category: uuid.UUID | None = Query(None),
                        code: str | None = Query(None)):
    return await svc.properties(category, code)


@router.post('/properties', response_model=MedPropertyOut,
             status_code=status.HTTP_201_CREATED)
async def add_my_property(body: MedPropertyIn, svc: MedAccessService = Depends()):
    return await svc.add_property(body)


# --- профиль здоровья: правка/закрытие/история записи (носитель — псевдоним) ---
@router.patch('/properties/{property_id}', response_model=MedPropertyOut)
async def update_my_property(property_id: uuid.UUID, body: dict,
                             svc: MedAccessService = Depends()):
    """Новое значение записи (рост, дозировка...); прежнее уходит в историю."""
    return await svc.update_property(property_id, body)


@router.delete('/properties/{property_id}', response_model=MedPropertyOut)
async def close_my_property(property_id: uuid.UUID, svc: MedAccessService = Depends()):
    """Закрыть запись (неактуальна); история сохраняется."""
    return await svc.close_property(property_id)


@router.get('/properties/{property_id}/history', response_model=List[MedPropertyOut])
async def my_property_history(property_id: uuid.UUID, svc: MedAccessService = Depends()):
    """Версии записи — история значений показателя."""
    return await svc.property_history(property_id)


# --- эпизоды (болезнь/травма) на псевдониме; доступ к {id} — за gate-проверкой ---
@router.get('/episodes', response_model=List[EpisodeOut])
async def my_episodes(svc: MedAccessService = Depends()):
    return await svc.episodes()


@router.post('/episodes', response_model=EpisodeOut, status_code=status.HTTP_201_CREATED)
async def open_episode(body: EpisodeIn, svc: MedAccessService = Depends()):
    return await svc.open_episode(body)


@router.get('/episodes/{episode_id}', response_model=EpisodeOut)
async def get_episode(episode_id: uuid.UUID, svc: MedAccessService = Depends()):
    return await svc.episode(episode_id)


@router.patch('/episodes/{episode_id}', response_model=EpisodeOut)
async def rename_episode(episode_id: uuid.UUID, body: EpisodeRename,
                         svc: MedAccessService = Depends()):
    """Назвать эпизод (после диагноза — при открытии имени ещё нет)."""
    return await svc.rename_episode(episode_id, body.name)


@router.get('/episodes/{episode_id}/history')
async def episode_history(episode_id: uuid.UUID, svc: MedAccessService = Depends()):
    """Журнал переходов состояния (кто когда перевёл — из темпоральной модели)."""
    return await svc.episode_history(episode_id)


@router.get('/episodes/{episode_id}/properties', response_model=List[MedPropertyOut])
async def episode_properties(episode_id: uuid.UUID, svc: MedAccessService = Depends(),
                             category: uuid.UUID | None = Query(None),
                             code: str | None = Query(None)):
    return await svc.episode_properties(episode_id, category, code)


@router.post('/episodes/{episode_id}/properties', response_model=MedPropertyOut,
             status_code=status.HTTP_201_CREATED)
async def add_episode_property(episode_id: uuid.UUID, body: MedPropertyIn,
                               svc: MedAccessService = Depends()):
    return await svc.add_episode_property(episode_id, body)


@router.get('/episodes/{episode_id}/state')
async def episode_state(episode_id: uuid.UUID, svc: MedAccessService = Depends()):
    return await svc.episode_state(episode_id)


@router.post('/episodes/{episode_id}/transition')
async def episode_transition(episode_id: uuid.UUID, body: Transition,
                             svc: MedAccessService = Depends()):
    return await svc.transition(episode_id, body.event)


# --- интервью: сбор анамнеза по протоколу (см. services/interview.py) ---
@router.post('/episodes/{episode_id}/interview')
async def interview_open(episode_id: uuid.UUID, svc: MedAccessService = Depends()):
    """Открыть интервью эпизода (идемпотентно) — возвращает состояние и вопрос."""
    return await svc.interview_open(episode_id)


@router.get('/episodes/{episode_id}/interview')
async def interview_state(episode_id: uuid.UUID, svc: MedAccessService = Depends()):
    return await svc.interview_state(episode_id)


@router.post('/episodes/{episode_id}/interview/answer')
async def interview_answer(episode_id: uuid.UUID, body: dict,
                           svc: MedAccessService = Depends()):
    """Ответ на текущий вопрос; сервер сам двигает автомат и возвращает следующий."""
    return await svc.interview_answer(episode_id, body)


@router.get('/episodes/{episode_id}/assess')
async def episode_assess(episode_id: uuid.UUID, svc: MedAccessService = Depends()):
    return await svc.assess(episode_id)


@router.post('/episodes/{episode_id}/evaluate', status_code=status.HTTP_202_ACCEPTED)
async def episode_evaluate(episode_id: uuid.UUID, svc: MedAccessService = Depends()):
    """Поставить ИИ-оценку в очередь; результат — Property(code='ddx') на эпизоде.
    Предположения для обсуждения с врачом, НЕ диагноз."""
    return await svc.evaluate(episode_id)


# --- документы/анализы: загрузка (-> блоб + метаданные + ИИ-разбор), список ---
# episode_id (Query) -> прикрепить к эпизоду (за воротами), иначе к самому псевдониму.
@router.post('/documents', response_model=DataOut, status_code=status.HTTP_201_CREATED)
async def upload_document(file: UploadFile,
                          name: str = Form(...),
                          code: str = Form(...),
                          category: uuid.UUID | None = Form(None),
                          episode_id: uuid.UUID | None = Query(None),
                          svc: MedAccessService = Depends()):
    content = await file.read()
    return await svc.upload_document(content, name, code, category,
                                     file.content_type or '', episode_id)


@router.get('/documents', response_model=List[DataOut])
async def my_documents(svc: MedAccessService = Depends(),
                       episode_id: uuid.UUID | None = Query(None)):
    return await svc.documents(episode_id)
