import uuid
from fastapi import APIRouter, Depends
from typing import List

from ..models.property import Property, PropertyCreate, PropertyUpdate, PropertyBase
from ..services.property import PropertyService

router = APIRouter(
    prefix='/property',
)


@router.get('/{property_id}', response_model=Property)
async def get_property_by_id(property_id: uuid.UUID, service: PropertyService = Depends()):
    property = await service.get_by_id(property_id)
    return property


@router.post('/', response_model=Property)
async def create_property(property_data: PropertyCreate, service: PropertyService = Depends()):
    property_ = await service.create(property_data)
    return property_


@router.post('/category_code', response_model=List[Property])
async def get_property_by_category_code(property_data: PropertyBase, service: PropertyService = Depends()):
    property_ = await service.get_by_code(property_data)
    return property_


@router.put('/{property_id}', response_model=Property)
async def update_property(property_id: uuid.UUID, property_data: PropertyUpdate, service: PropertyService = Depends()):
    property_ = await service.update(property_id, property_data)
    return property_


@router.delete('/{property_id}', response_model=Property)
async def delete_property(property_id: uuid.UUID, service: PropertyService = Depends()):
    property_ = await service.expire(property_id)
    return property_
