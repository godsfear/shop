import uuid
from typing import List

from fastapi import APIRouter, Depends, status

from ..models.auth import TokenPayload
from ..models.company import Company, CompanyCreate, CompanyUpdate, CompanyFilter
from ..services.auth import get_token_payload
from ..services.company import CompanyService
from ..services.consent import ConsentService

# identity-домен: детали и правки — управляющему/по согласию; создатель новой
# компании автоматически становится её первым управляющим (см. CompanyService).
# find оставлен под токеном — реестр юрлиц обычно доступен для поиска.
router = APIRouter(prefix='/company', tags=['company'])


@router.post('/find', response_model=List[Company])
async def find_company(flt: CompanyFilter, service: CompanyService = Depends(),
                       payload: TokenPayload = Depends(get_token_payload)):
    return await service.find(flt)


@router.get('/{company_id}', response_model=Company)
async def get_company_by_id(company_id: uuid.UUID, service: CompanyService = Depends(),
                            consent: ConsentService = Depends(),
                            payload: TokenPayload = Depends(get_token_payload)):
    await consent.ensure_access('company', company_id, payload)
    return await service.get_by_id(company_id)


@router.post('/', response_model=Company, status_code=status.HTTP_201_CREATED)
async def create_company(data: CompanyCreate, service: CompanyService = Depends(),
                         payload: TokenPayload = Depends(get_token_payload)):
    return await service.create(data, creator=payload.sub)


@router.patch('/{company_id}', response_model=Company)
async def update_company(company_id: uuid.UUID, data: CompanyUpdate,
                         service: CompanyService = Depends(),
                         consent: ConsentService = Depends(),
                         payload: TokenPayload = Depends(get_token_payload)):
    await consent.ensure_access('company', company_id, payload, write=True)
    return await service.update(company_id, data)


@router.delete('/{company_id}', response_model=Company)
async def delete_company(company_id: uuid.UUID, service: CompanyService = Depends(),
                         consent: ConsentService = Depends(),
                         payload: TokenPayload = Depends(get_token_payload)):
    await consent.ensure_access('company', company_id, payload, write=True)
    return await service.expire(company_id)
