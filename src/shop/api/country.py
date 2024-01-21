import uuid
from fastapi import APIRouter, Depends
from typing import List, Annotated

from shop.models import Country, CountryCreate, CountryUpdate, CountryGet
from shop.services import CountryService

router = APIRouter(prefix='/country', tags=['country'])


@router.get('/all', response_model=List[Country])
async def get_country(service: Annotated[CountryService, Depends(CountryService)]):
    country = await service.get_all()
    return country


@router.get('/{country_id}', response_model=Country)
async def get_country_by_id(country_id: uuid.UUID, service: Annotated[CountryService, Depends(CountryService)]):
    country = await service.get_by_id(country_id)
    return country


@router.post('/', response_model=Country)
async def create_country(country_data: CountryCreate, service: Annotated[CountryService, Depends(CountryService)]):
    country = await service.create(country_data)
    return country


@router.post('/by_code', response_model=Country)
async def get_country_by_category_code(country_data: CountryGet,
                                       service: Annotated[CountryService, Depends(CountryService)]):
    country = await service.get_by_code(country_data)
    return country


@router.put('/{country_id}', response_model=Country)
async def update_country(country_id: uuid.UUID,
                         country_data: CountryUpdate,
                         service: Annotated[CountryService, Depends(CountryService)]):
    country = await service.update(country_id, country_data)
    return country


@router.delete('/{country_id}', response_model=Country)
async def delete_country(country_id: uuid.UUID, service: Annotated[CountryService, Depends(CountryService)]):
    country = await service.expire(country_id)
    return country
