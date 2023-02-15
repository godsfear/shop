import uuid
from fastapi import APIRouter, Depends
from typing import List

from fastapi import Response
from starlette import status

from ..models.entity import Entity, EntityCreate, EntityUpdate
from ..services.entity import EntityService

router = APIRouter(
    prefix='/entity',
)


@router.get('/', response_model=List[Entity])
async def get_entity(service: EntityService = Depends()):
    entity = await service.get_all()
    return entity


@router.get('/{entity_id}', response_model=Entity)
async def get_entity_by_id(entity_id: uuid.UUID, service: EntityService = Depends()):
    entity = await service.get_by_id(entity_id)
    return entity


@router.post('/', response_model=Entity)
async def create_entity(entity_data: EntityCreate, service: EntityService = Depends()):
    entity = await service.create(entity_data)
    return entity


@router.put('/{entity_id}', response_model=Entity)
async def update_entity(entity_id: uuid.UUID, entity_data: EntityUpdate, service: EntityService = Depends()):
    entity = await service.update(entity_id, entity_data)
    return entity


@router.delete('/{entity_id}')
async def delete_entity(entity_id: uuid.UUID, service: EntityService = Depends()):
    service.delete(entity_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
