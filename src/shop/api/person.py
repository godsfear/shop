import uuid

from fastapi import APIRouter, Depends, status

from ..models.auth import TokenPayload
from ..models.person import Person, PersonCreate, PersonUpdate
from ..services.auth import get_token_payload
from ..services.person import PersonService

# домен личности: все операции только под токеном, поиска нет — доступ по id
router = APIRouter(prefix='/person', tags=['person'])


@router.get('/{person_id}', response_model=Person)
async def get_person_by_id(person_id: uuid.UUID, service: PersonService = Depends(),
                           payload: TokenPayload = Depends(get_token_payload)):
    return await service.get_by_id(person_id)


@router.post('/', response_model=Person, status_code=status.HTTP_201_CREATED)
async def create_person(data: PersonCreate, service: PersonService = Depends(),
                        payload: TokenPayload = Depends(get_token_payload)):
    return await service.create(data)


@router.patch('/{person_id}', response_model=Person)
async def update_person(person_id: uuid.UUID, data: PersonUpdate,
                        service: PersonService = Depends(),
                        payload: TokenPayload = Depends(get_token_payload)):
    return await service.update(person_id, data)


@router.delete('/{person_id}', response_model=Person)
async def delete_person(person_id: uuid.UUID, service: PersonService = Depends(),
                        payload: TokenPayload = Depends(get_token_payload)):
    return await service.expire(person_id)
