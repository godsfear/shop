import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..models.auth import TokenPayload
from ..models.user import Contact, User, UserUpdate, UserRoles
from ..services.user import UserService
from ..services.auth import get_token_payload, require_roles
from ..settings import settings

router = APIRouter(prefix='/user', tags=['user'])


def _self_or_admin(user_id: uuid.UUID, payload: TokenPayload) -> None:
    if payload.sub != user_id and settings.admin_role not in payload.roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='можно менять только свою учётную запись')


@router.get('/all', response_model=List[User])
async def get_users(service: UserService = Depends(),
                    payload: TokenPayload = Depends(get_token_payload),
                    limit: int = Query(100, ge=1, le=1000),
                    offset: int = Query(0, ge=0)):
    return await service.get_all(limit=limit, offset=offset)


@router.post('/find', response_model=User)
async def find_user_by_contact(contact: Contact, service: UserService = Depends(),
                               payload: TokenPayload = Depends(get_token_payload)):
    prop = contact.email or contact.phone
    if not prop:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Нужен email или phone')
    found = await service.get_by_contact(prop)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return found


@router.get('/{user_id}', response_model=User)
async def get_user_by_id(user_id: uuid.UUID, service: UserService = Depends(),
                         payload: TokenPayload = Depends(get_token_payload)):
    return await service.get_by_id(user_id)


@router.patch('/{user_id}/roles', response_model=User)
async def set_user_roles(user_id: uuid.UUID, data: UserRoles,
                         service: UserService = Depends(),
                         payload: TokenPayload = Depends(require_roles(settings.admin_role))):
    return await service.set_roles(user_id, data.roles)


@router.patch('/{user_id}', response_model=User)
async def update_user(user_id: uuid.UUID, user_data: UserUpdate,
                      service: UserService = Depends(),
                      payload: TokenPayload = Depends(get_token_payload)):
    _self_or_admin(user_id, payload)
    return await service.update(user_id, user_data)


@router.delete('/{user_id}', response_model=User)
async def delete_user(user_id: uuid.UUID, service: UserService = Depends(),
                      payload: TokenPayload = Depends(get_token_payload)):
    _self_or_admin(user_id, payload)
    return await service.expire(user_id)
