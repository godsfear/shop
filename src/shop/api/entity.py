import uuid
from typing import List

from fastapi import APIRouter, Depends, status

from ..models.entity import Entity, EntityCreate, EntityUpdate, EntityFilter
from ..services.entity import EntityService

router = APIRouter(prefix='/entity', tags=['entity'])


@router.get('/all', response_model=List[Entity])
async def get_entities(service: EntityService = Depends()):
    return await service.get_all()


@router.post('/find', response_model=List[Entity])
async def find_entity(flt: EntityFilter, service: EntityService = Depends()):
    return await service.find(flt)


@router.get('/{entity_id}', response_model=Entity)
async def get_entity_by_id(entity_id: uuid.UUID, service: EntityService = Depends()):
    return await service.get_by_id(entity_id)


@router.post('/', response_model=Entity, status_code=status.HTTP_201_CREATED)
async def create_entity(entity_data: EntityCreate, service: EntityService = Depends()):
    return await service.create(entity_data)


@router.patch('/{entity_id}', response_model=Entity)
async def update_entity(entity_id: uuid.UUID, entity_data: EntityUpdate,
                        service: EntityService = Depends()):
    return await service.update(entity_id, entity_data)


@router.delete('/{entity_id}', response_model=Entity)
async def delete_entity(entity_id: uuid.UUID, service: EntityService = Depends()):
    return await service.expire(entity_id)
