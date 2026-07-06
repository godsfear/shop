import uuid
from typing import List

from fastapi import APIRouter, Depends, status

from ..models.auth import TokenPayload
from ..models.category import Category, CategoryCreate, CategoryUpdate, CategoryFilter
from ..services.auth import get_token_payload
from ..services.category import CategoryService

router = APIRouter(prefix='/category', tags=['category'])


@router.post('/find', response_model=List[Category])
async def find_category(flt: CategoryFilter, service: CategoryService = Depends()):
    return await service.find(flt)


@router.get('/{category_id}', response_model=Category)
async def get_category_by_id(category_id: uuid.UUID, service: CategoryService = Depends()):
    return await service.get_by_id(category_id)


@router.post('/', response_model=Category, status_code=status.HTTP_201_CREATED)
async def create_category(category_data: CategoryCreate, service: CategoryService = Depends(),
                          payload: TokenPayload = Depends(get_token_payload)):
    return await service.create(category_data, creator=payload.sub)


@router.patch('/{category_id}', response_model=Category)
async def update_category(category_id: uuid.UUID, category_data: CategoryUpdate,
                          service: CategoryService = Depends(),
                          payload: TokenPayload = Depends(get_token_payload)):
    return await service.update(category_id, category_data)


@router.delete('/{category_id}', response_model=Category)
async def delete_category(category_id: uuid.UUID, service: CategoryService = Depends(),
                          payload: TokenPayload = Depends(get_token_payload)):
    return await service.expire(category_id)
