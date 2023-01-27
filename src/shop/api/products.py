import uuid
from fastapi import APIRouter, Depends
from typing import List

from fastapi import Response
from starlette import status

from ..models.products import Products, ProductsCreate, ProductsUpdate
from ..services.products import ProductsService

router = APIRouter(
    prefix='/products',
)


@router.get('/', response_model=List[Products])
async def get_products(service: ProductsService = Depends()):
    products = await service.get_all()
    return products


@router.get('/{product_id}', response_model=Products)
async def get_product_by_id(product_id: uuid.UUID, service: ProductsService = Depends()):
    return service.get_by_id(product_id)


@router.post('/', response_model=Products)
async def create_products(products_data: ProductsCreate, service: ProductsService = Depends()):
    product = await service.create(products_data)
    return product


@router.put('/{product_id}', response_model=Products)
async def update_product(product_id: uuid.UUID, product_data: ProductsUpdate, service: ProductsService = Depends()):
    return service.update(product_id, product_data)


@router.delete('/{product_id}')
async def delete_product(product_id: uuid.UUID, service: ProductsService = Depends()):
    service.delete(product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
