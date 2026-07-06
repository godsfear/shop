import uuid
from typing import List

from fastapi import APIRouter, Depends, status

from ..models.auth import TokenPayload
from ..models.place import Place, PlaceCreate, PlaceUpdate, PlaceFilter
from ..services.auth import get_token_payload
from ..services.place import PlaceService

router = APIRouter(prefix='/place', tags=['place'])


@router.post('/find', response_model=List[Place])
async def find_place(flt: PlaceFilter, service: PlaceService = Depends()):
    return await service.find(flt)


@router.get('/{place_id}', response_model=Place)
async def get_place_by_id(place_id: uuid.UUID, service: PlaceService = Depends()):
    return await service.get_by_id(place_id)


@router.post('/', response_model=Place, status_code=status.HTTP_201_CREATED)
async def create_place(data: PlaceCreate, service: PlaceService = Depends(),
                       payload: TokenPayload = Depends(get_token_payload)):
    return await service.create(data, creator=payload.sub)


@router.patch('/{place_id}', response_model=Place)
async def update_place(place_id: uuid.UUID, data: PlaceUpdate,
                       service: PlaceService = Depends(),
                       payload: TokenPayload = Depends(get_token_payload)):
    return await service.update(place_id, data)


@router.delete('/{place_id}', response_model=Place)
async def delete_place(place_id: uuid.UUID, service: PlaceService = Depends(),
                       payload: TokenPayload = Depends(get_token_payload)):
    return await service.expire(place_id)
