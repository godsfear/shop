from fastapi import APIRouter, Depends
from typing import List

from fastapi import Response
from starlette import status

from ..models.categories import Categories, CategoriesCreate, CategoriesUpdate
from ..services.categories import CategoriesService

router = APIRouter(
    prefix='/categories',
)


@router.get('/', response_model=List[Categories])
async def get_categories(service: CategoriesService = Depends()):
    return service.get_all()


@router.get('/{category_id}', response_model=Categories)
async def get_category_by_id(category_id: int, service: CategoriesService = Depends()):
    return service.get_by_id(category_id)


@router.post('/', response_model=Categories)
async def create_categories(categories_data: CategoriesCreate, service: CategoriesService = Depends()):
    return service.create(categories_data)


@router.put('/{category_id}', response_model=Categories)
async def update_category(category_id: int, category_data: CategoriesUpdate, service: CategoriesService = Depends()):
    return service.update(category_id, category_data)


@router.delete('/{category_id}')
async def delete_category(category_id: int, service: CategoriesService = Depends()):
    service.delete(category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
