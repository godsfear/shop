from typing import List
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from starlette import status

from ..database import get_session
from .. import tables
from ..models.products import ProductsCreate, ProductsUpdate


class ProductsService:
    def __init__(self, session: Session = Depends(get_session)):
        self.session = session

    def _get(self, product_id: int) -> tables.Products:
        products = self.session.query(tables.Products).filter_by(id=product_id).first()
        if not products:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return products

    def get_all(self) -> List[tables.Products]:
        return self.session.query(tables.Products).all()

    def get_by_id(self, product_id: int) -> tables.Products:
        return self._get(product_id)

    def create(self, products_data: ProductsCreate) -> tables.Products:
        products = tables.Products(**products_data.dict())
        self.session.add(products)
        self.session.commit()
        return products

    def update(self, product_id: int, product_data: ProductsUpdate) -> tables.Products:
        products = self._get(product_id)
        for field, value in product_data:
            setattr(products, field, value)
        self.session.commit()
        return products

    def delete(self, product_id: int):
        products = self._get(product_id)
        self.session.delete(products)
        self.session.commit()
