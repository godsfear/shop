import uuid
from fastapi import APIRouter, Depends
from typing import List

from ..models.address import Address, AddressCreate, AddressUpdate, AddressBase
from ..services.address import AddressService

router = APIRouter(prefix='/address', tags=['address'])


@router.get('/all', response_model=List[Address])
async def get_address(service: AddressService = Depends()):
    address = await service.get_all()
    return address


@router.get('/{address_id}', response_model=Address)
async def get_address_by_id(address_id: uuid.UUID, service: AddressService = Depends()):
    address = await service.get_by_id(address_id)
    return address


@router.post('/', response_model=Address)
async def create_address(address_data: AddressCreate, service: AddressService = Depends()):
    address = await service.create(address_data)
    return address


@router.put('/{address_id}', response_model=Address)
async def update_address(address_id: uuid.UUID, address_data: AddressUpdate, service: AddressService = Depends()):
    address = await service.update(address_id, address_data)
    return address


@router.delete('/{address_id}', response_model=Address)
async def delete_address(address_id: uuid.UUID, service: AddressService = Depends()):
    address = await service.expire(address_id)
    return address
