import uuid
from typing import List

from fastapi import APIRouter, Depends, status

from ..models.currency import Currency, CurrencyCreate, CurrencyUpdate, CurrencyFilter
from ..services.currency import CurrencyService

router = APIRouter(prefix='/currency', tags=['currency'])


@router.post('/find', response_model=List[Currency])
async def find_currency(flt: CurrencyFilter, service: CurrencyService = Depends()):
    return await service.find(flt)


@router.get('/{currency_id}', response_model=Currency)
async def get_currency_by_id(currency_id: uuid.UUID, service: CurrencyService = Depends()):
    return await service.get_by_id(currency_id)


@router.post('/', response_model=Currency, status_code=status.HTTP_201_CREATED)
async def create_currency(currency_data: CurrencyCreate, service: CurrencyService = Depends()):
    return await service.create(currency_data)


@router.patch('/by_code', response_model=Currency)
async def update_currency_by_code(flt: CurrencyFilter, currency_data: CurrencyUpdate,
                                  service: CurrencyService = Depends()):
    return await service.update_by_code(flt, currency_data)


@router.patch('/{currency_id}', response_model=Currency)
async def update_currency(currency_id: uuid.UUID, currency_data: CurrencyUpdate,
                          service: CurrencyService = Depends()):
    return await service.update(currency_id, currency_data)


@router.delete('/{currency_id}', response_model=Currency)
async def delete_currency(currency_id: uuid.UUID, service: CurrencyService = Depends()):
    return await service.expire(currency_id)
