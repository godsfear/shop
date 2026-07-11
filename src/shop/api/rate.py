import uuid
from typing import List

from fastapi import APIRouter, Depends, status

from ..models.auth import TokenPayload
from ..models.rate import Rate, RateCreate, RateUpdate, RateFilter
from ..services.auth import require_admin
from ..services.rate import RateService

router = APIRouter(prefix='/rate', tags=['rate'])


@router.post('/find', response_model=List[Rate])
async def find_rate(flt: RateFilter, service: RateService = Depends()):
    return await service.find(flt)


@router.get('/{rate_id}', response_model=Rate)
async def get_rate_by_id(rate_id: uuid.UUID, service: RateService = Depends()):
    return await service.get_by_id(rate_id)


@router.post('/', response_model=Rate, status_code=status.HTTP_201_CREATED)
async def create_rate(data: RateCreate, service: RateService = Depends(),
                      payload: TokenPayload = Depends(require_admin)):
    return await service.create(data, creator=payload.sub)


@router.patch('/{rate_id}', response_model=Rate)
async def update_rate(rate_id: uuid.UUID, data: RateUpdate,
                      service: RateService = Depends(),
                      payload: TokenPayload = Depends(require_admin)):
    return await service.update(rate_id, data)


@router.delete('/{rate_id}', response_model=Rate)
async def delete_rate(rate_id: uuid.UUID, service: RateService = Depends(),
                      payload: TokenPayload = Depends(require_admin)):
    return await service.expire(rate_id)
