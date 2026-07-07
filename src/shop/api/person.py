import uuid

from fastapi import APIRouter, Depends, status

from ..models.auth import TokenPayload
from ..models.person import Person, PersonCreate, PersonUpdate
from ..services.auth import get_token_payload
from ..services.consent import ConsentService
from ..services.person import PersonService

# домен личности, consent-first: читает владелец/управляющий/админ или
# обладатель действующего согласия scope='identity'; правит — только
# владелец/управляющий/админ. Поиска нет — доступ точечный, по id.
router = APIRouter(prefix='/person', tags=['person'])


@router.get('/{person_id}', response_model=Person)
async def get_person_by_id(person_id: uuid.UUID, service: PersonService = Depends(),
                           consent: ConsentService = Depends(),
                           payload: TokenPayload = Depends(get_token_payload)):
    await consent.ensure_access('person', person_id, payload)
    return await service.get_by_id(person_id)


@router.post('/', response_model=Person, status_code=status.HTTP_201_CREATED)
async def create_person(data: PersonCreate, service: PersonService = Depends(),
                        payload: TokenPayload = Depends(get_token_payload)):
    """Создание новой персоны (регистратура и т.п.) — субъекта ещё нет,
    согласовывать не у кого; достаточно аутентификации."""
    return await service.create(data)


@router.patch('/{person_id}', response_model=Person)
async def update_person(person_id: uuid.UUID, data: PersonUpdate,
                        service: PersonService = Depends(),
                        consent: ConsentService = Depends(),
                        payload: TokenPayload = Depends(get_token_payload)):
    await consent.ensure_access('person', person_id, payload, write=True)
    return await service.update(person_id, data)


@router.delete('/{person_id}', response_model=Person)
async def delete_person(person_id: uuid.UUID, service: PersonService = Depends(),
                        consent: ConsentService = Depends(),
                        payload: TokenPayload = Depends(get_token_payload)):
    await consent.ensure_access('person', person_id, payload, write=True)
    return await service.expire(person_id)
