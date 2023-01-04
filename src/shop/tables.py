import sqlalchemy as sa
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

product_categories = sa.Table(
    "product_categories",
    Base.metadata,
    sa.Column("product_id", sa.ForeignKey("products.id"), primary_key=True),
    sa.Column("category_id", sa.ForeignKey("categories.id"), primary_key=True),
)


class Products(Base):
    __tablename__: str = 'products'

    id = sa.Column(sa.Integer, unique=True, primary_key=True, autoincrement=True, nullable=False)
    name = sa.Column(sa.String, index=True)
    description = sa.Column(sa.String, nullable=True)
    category = relationship("Categories", secondary=product_categories, back_populates="product")

    def __repr__(self):
        return f'{self.id} {self.name}'


class Categories(Base):
    __tablename__: str = 'categories'

    id = sa.Column(sa.Integer, unique=True, primary_key=True, autoincrement=True, nullable=False)
    name = sa.Column(sa.String, index=True)
    description = sa.Column(sa.String, nullable=True)
    product = relationship("Products", secondary=product_categories, back_populates="category")

    def __repr__(self):
        return f'{self.id} {self.name}'
