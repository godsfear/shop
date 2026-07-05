import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from ..models.user import Contact, User, UserCreate, UserUpdate
from ..services.user import UserService
from ..services.auth import AuthService

router = APIRouter(prefix='/user', tags=['user'])


@router.get('/all', response_model=List[User])
async def get_users(service: UserService = Depends(),
                    user: User = Depends(AuthService.get_current_user)):
    return await service.get_all()


@router.post('/find', response_model=User)
async def find_user_by_contact(contact: Contact, service: UserService = Depends(),
                               user: User = Depends(AuthService.get_current_user)):
    prop = contact.email or contact.phone
    if not prop:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Нужен email или phone')
    found = await service.get_by_contact(prop)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return found


@router.get('/{user_id}', response_model=User)
async def get_user_by_id(user_id: uuid.UUID, service: UserService = Depends(),
                         user: User = Depends(AuthService.get_current_user)):
    return await service.get_by_id(user_id)


@router.post('/', response_model=User, status_code=status.HTTP_201_CREATED)
async def create_user(user_data: UserCreate, service: UserService = Depends()):
    return await service.create(user_data)


@router.patch('/{user_id}', response_model=User)
async def update_user(user_id: uuid.UUID, user_data: UserUpdate, service: UserService = Depends()):
    return await service.update(user_id, user_data)


@router.delete('/{user_id}', response_model=User)
async def delete_user(user_id: uuid.UUID, service: UserService = Depends()):
    return await service.expire(user_id)
