import uuid
from typing import List, Annotated

from fastapi import APIRouter, Depends, status

from shop.models import Country, CountryCreate, CountryUpdate, CountryFilter, TokenPayload
from shop.services import CountryService
from shop.services.auth import require_admin

router = APIRouter(prefix='/country', tags=['country'])


@router.get('/all', response_model=List[Country])
async def get_countries(service: Annotated[CountryService, Depends(CountryService)]):
    return await service.get_all()


@router.post('/find', response_model=Country)
async def find_country(flt: CountryFilter, service: Annotated[CountryService, Depends(CountryService)]):
    return await service.find(flt)


@router.get('/{country_id}', response_model=Country)
async def get_country_by_id(country_id: uuid.UUID, service: Annotated[CountryService, Depends(CountryService)]):
    return await service.get_by_id(country_id)


@router.post('/', response_model=Country, status_code=status.HTTP_201_CREATED)
async def create_country(country_data: CountryCreate,
                         service: Annotated[CountryService, Depends(CountryService)],
                         payload: Annotated[TokenPayload, Depends(require_admin)]):
    return await service.create(country_data, creator=payload.sub)


@router.patch('/{country_id}', response_model=Country)
async def update_country(country_id: uuid.UUID, country_data: CountryUpdate,
                         service: Annotated[CountryService, Depends(CountryService)],
                         payload: Annotated[TokenPayload, Depends(require_admin)]):
    return await service.update(country_id, country_data)


@router.delete('/{country_id}', response_model=Country)
async def delete_country(country_id: uuid.UUID,
                         service: Annotated[CountryService, Depends(CountryService)],
                         payload: Annotated[TokenPayload, Depends(require_admin)]):
    return await service.expire(country_id)
