import uuid
from typing import List

from fastapi import APIRouter, Depends, Query, status

from ..models.auth import TokenPayload
from ..models.entity import Entity, EntityCreate, EntityUpdate, EntityFilter
from ..services.auth import get_token_payload, require_admin
from ..services.entity import EntityService

# generic-CRUD по Entity — админ-инструмент: среди строк есть операционные
# данные (эпизоды на псевдонимах); прикладной путь пациента — /me/*
router = APIRouter(prefix='/entity', tags=['entity'],
                   dependencies=[Depends(require_admin)])


@router.get('/all', response_model=List[Entity])
async def get_entities(service: EntityService = Depends(),
                       limit: int = Query(100, ge=1, le=1000),
                       offset: int = Query(0, ge=0)):
    return await service.get_all(limit=limit, offset=offset)


@router.post('/find', response_model=List[Entity])
async def find_entity(flt: EntityFilter, service: EntityService = Depends()):
    return await service.find(flt)


@router.get('/{entity_id}', response_model=Entity)
async def get_entity_by_id(entity_id: uuid.UUID, service: EntityService = Depends()):
    return await service.get_by_id(entity_id)


@router.post('/', response_model=Entity, status_code=status.HTTP_201_CREATED)
async def create_entity(entity_data: EntityCreate, service: EntityService = Depends(),
                        payload: TokenPayload = Depends(get_token_payload)):
    return await service.create(entity_data, creator=payload.sub)


@router.patch('/{entity_id}', response_model=Entity)
async def update_entity(entity_id: uuid.UUID, entity_data: EntityUpdate,
                        service: EntityService = Depends(),
                        payload: TokenPayload = Depends(get_token_payload)):
    return await service.update(entity_id, entity_data)


@router.delete('/{entity_id}', response_model=Entity)
async def delete_entity(entity_id: uuid.UUID, service: EntityService = Depends(),
                        payload: TokenPayload = Depends(get_token_payload)):
    return await service.expire(entity_id)
