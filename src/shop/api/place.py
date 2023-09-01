import uuid
from fastapi import APIRouter, Depends
from typing import List

from ..models.place import Place, PlaceCreate, PlaceUpdate, PlaceBase
from ..services.place import PlaceService

router = APIRouter(prefix='/place', tags=['place'])


@router.get('/{place_id}', response_model=Place)
async def get_place_by_id(place_id: uuid.UUID, service: PlaceService = Depends()):
    place = await service.get_by_id(place_id)
    return place


@router.post('/', response_model=Place)
async def create_place(place_data: PlaceCreate, service: PlaceService = Depends()):
    place = await service.create(place_data)
    return place


@router.post('/by_index', response_model=List[Place])
async def get_place_by_category_code(place_data: PlaceBase, service: PlaceService = Depends()):
    place = await service.place_idx(place_data)
    return place


@router.put('/{place_id}', response_model=Place)
async def update_place(place_id: uuid.UUID, place_data: PlaceUpdate, service: PlaceService = Depends()):
    place = await service.update(place_id, place_data)
    return place


@router.delete('/{place_id}', response_model=Place)
async def delete_place(place_id: uuid.UUID, service: PlaceService = Depends()):
    place = await service.expire(place_id)
    return place
