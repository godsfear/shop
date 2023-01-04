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
def get_products(service: ProductsService = Depends()):
    return service.get_all()


@router.get('/{product_id}', response_model=Products)
def get_product_by_id(product_id: int, service: ProductsService = Depends()):
    return service.get_by_id(product_id)


@router.post('/', response_model=Products)
def create_products(products_data: ProductsCreate, service: ProductsService = Depends()):
    return service.create(products_data)


@router.put('/{product_id}', response_model=Products)
def update_product(product_id: int, product_data: ProductsUpdate, service: ProductsService = Depends()):
    return service.update(product_id, product_data)


@router.delete('/{product_id}')
def delete_product(product_id: int, service: ProductsService = Depends()):
    service.delete(product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
