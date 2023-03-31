import uuid
from fastapi import APIRouter, Depends
from typing import List

from ..models.currency import Currency, CurrencyCreate, CurrencyUpdate, CurrencyBase
from ..services.currency import CurrencyService

router = APIRouter(prefix='/currency',tags=['currency'])


@router.get('/{currency_id}', response_model=Currency)
async def get_currency_by_id(currency_id: uuid.UUID, service: CurrencyService = Depends()):
    currency = await service.get_by_id(currency_id)
    return currency


@router.post('/', response_model=Currency)
async def create_currency(currency_data: CurrencyCreate, service: CurrencyService = Depends()):
    currency = await service.create(currency_data)
    return currency


@router.post('/category_code', response_model=Currency)
async def get_currency_by_category_code(currency_data: CurrencyBase, service: CurrencyService = Depends()):
    currency = await service.get_by_category_code(currency_data)
    return currency


@router.post('/category', response_model=List[Currency])
async def get_currency_by_category_code(currency_data: CurrencyBase, service: CurrencyService = Depends()):
    currency = await service.get_by_category(currency_data)
    return currency


@router.put('/{currency_id}', response_model=Currency)
async def update_currency(currency_id: uuid.UUID, currency_data: CurrencyUpdate, service: CurrencyService = Depends()):
    currency = await service.update(currency_id, currency_data)
    return currency


@router.put('/category_code', response_model=Currency)
async def update_currency_by_category_code(currency_data: CurrencyUpdate,service: CurrencyService = Depends()):
    currency = await service.update_by_code(currency_data)
    return currency


@router.delete('/{currency_id}', response_model=Currency)
async def delete_currency(currency_id: uuid.UUID, service: CurrencyService = Depends()):
    currency = await service.expire(currency_id)
    return currency
