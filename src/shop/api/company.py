import uuid
from fastapi import APIRouter, Depends
from typing import List

from ..models.company import Company, CompanyCreate, CompanyUpdate, CompanyBase
from ..services.company import CompanyService

router = APIRouter(prefix='/company', tags=['company'])


@router.get('/all', response_model=List[Company])
async def get_company(service: CompanyService = Depends()):
    company = await service.get_all()
    return company


@router.get('/{company_id}', response_model=Company)
async def get_company_by_id(company_id: uuid.UUID, service: CompanyService = Depends()):
    company = await service.get_by_id(company_id)
    return company


@router.post('/', response_model=Company)
async def create_company(company_data: CompanyCreate, service: CompanyService = Depends()):
    company = await service.create(company_data)
    return company


@router.post('/category_code', response_model=List[Company])
async def get_company_by_country_code(company_data: CompanyBase, service: CompanyService = Depends()):
    company = await service.get_by_country_code(company_data)
    return company


@router.put('/{company_id}', response_model=Company)
async def update_company(company_id: uuid.UUID, company_data: CompanyUpdate, service: CompanyService = Depends()):
    company = await service.update(company_id, company_data)
    return company


@router.delete('/{company_id}', response_model=Company)
async def delete_company(company_id: uuid.UUID, service: CompanyService = Depends()):
    company = await service.expire(company_id)
    return company
