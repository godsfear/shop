import uuid
from sqlalchemy import Table, Column, String, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID

Base = declarative_base()

product_category = Table(
    "product_categories",
    Base.metadata,
    Column("product_id", ForeignKey("products.id"), primary_key=True),
    Column("category_id", ForeignKey("categories.id"), primary_key=True),
)


class Products(Base):
    __tablename__: str = 'products'

    id = Column(UUID(as_uuid=True), unique=True, primary_key=True, nullable=False, default=uuid.uuid4)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    category = relationship("Categories", secondary=product_category, back_populates="product")

    def __repr__(self):
        return f'id={self.id}; name={self.name}'


class Categories(Base):
    __tablename__: str = 'categories'

    id = Column(UUID(as_uuid=True), unique=True, primary_key=True, nullable=False, default=uuid.uuid4)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    product = relationship("Products", secondary=product_category, back_populates="category")

    def __repr__(self):
        return f'id={self.id}; name={self.name}'
