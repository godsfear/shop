import uuid
from fastapi import APIRouter, Depends
from typing import List

from ..models.user import User, UserCreate, UserUpdate, UserBase
from ..services.user import UserService
from ..services.auth import AuthService

router = APIRouter(
    prefix='/user',
)


@router.get('/all', response_model=List[User])
async def get_user(service: UserService = Depends(), user: User = Depends(AuthService.get_current_user)):
    if user:
        user = await service.get_all()
        return user


@router.get('/{user_id}', response_model=User)
async def get_user_by_id(
                            user_id: uuid.UUID, service: UserService = Depends(),
                            user: User = Depends(AuthService.get_current_user)
                         ):
    if user:
        user = await service.get_by_id(user_id)
        return user


@router.post('/signup', response_model=User)
async def create_user(user_data: UserCreate, service: UserService = Depends()):
    user = await service.create(user_data)
    return user


@router.post('/name', response_model=List[User])
async def get_user_by_name(user_data: UserBase, service: UserService = Depends()):
    user = await service.get_by_prop(user_data.email if user_data.email else user_data.phone)
    return user


@router.put('/{user_id}', response_model=User)
async def update_user(user_id: uuid.UUID, user_data: UserUpdate, service: UserService = Depends()):
    user = await service.update(user_id, user_data)
    return user


@router.delete('/{user_id}', response_model=User)
async def delete_user(user_id: uuid.UUID, service: UserService = Depends()):
    user = await service.expire(user_id)
    return user
