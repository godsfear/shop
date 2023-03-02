import uuid
from fastapi import APIRouter, Depends
from typing import List

from ..models.category import Category, CategoryCreate, CategoryUpdate, CategoryBase
from ..services.category import CategoryService

router = APIRouter(
    prefix='/category',
)


@router.get('/all', response_model=List[Category])
async def get_category(service: CategoryService = Depends()):
    category = await service.get_all()
    return category


@router.get('/{category_id}', response_model=Category)
async def get_category_by_id(category_id: uuid.UUID, service: CategoryService = Depends()):
    category = await service.get_by_id(category_id)
    return category


@router.post('/', response_model=Category)
async def create_category(category_data: CategoryCreate, service: CategoryService = Depends()):
    category = await service.create(category_data)
    return category


@router.post('/category_code', response_model=List[Category])
async def get_category_by_category_code(category_data: CategoryBase, service: CategoryService = Depends()):
    category = await service.get_by_category_code(category_data)
    return category


@router.put('/{category_id}', response_model=Category)
async def update_category(category_id: uuid.UUID, category_data: CategoryUpdate, service: CategoryService = Depends()):
    category = await service.update(category_id, category_data)
    return category


@router.delete('/{category_id}', response_model=Category)
async def delete_category(category_id: uuid.UUID, service: CategoryService = Depends()):
    category = await service.expire(category_id)
    return category
