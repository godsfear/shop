import uuid
from fastapi import APIRouter, Depends
from typing import List

from ..models.person import Person, PersonCreate, PersonUpdate, PersonBase
from ..services.person import PersonService

router = APIRouter(prefix='/person', tags=['person'])


@router.get('/all', response_model=List[Person])
async def get_person(service: PersonService = Depends()):
    person = await service.get_all()
    return person


@router.get('/{person_id}', response_model=Person)
async def get_person_by_id(person_id: uuid.UUID, service: PersonService = Depends()):
    person = await service.get_by_id(person_id)
    return person


@router.post('/', response_model=Person)
async def create_person(person_data: PersonCreate, service: PersonService = Depends()):
    person = await service.create(person_data)
    return person


@router.put('/{person_id}', response_model=Person)
async def update_person(person_id: uuid.UUID, person_data: PersonUpdate, service: PersonService = Depends()):
    person = await service.update(person_id, person_data)
    return person


@router.delete('/{person_id}', response_model=Person)
async def delete_person(person_id: uuid.UUID, service: PersonService = Depends()):
    person = await service.expire(person_id)
    return person
