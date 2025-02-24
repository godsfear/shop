from geoalchemy2 import Geography
import datetime
import uuid6

from typing import List, Optional, Annotated
from sqlalchemy import (String, ForeignKey, DateTime, Date, Index, Integer, Numeric, Boolean, CheckConstraint, MetaData,
                        or_)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, BYTEA, SMALLINT, ARRAY
from sqlalchemy.orm import DeclarativeBase, declared_attr, Mapped, mapped_column
from sqlalchemy.sql import func


UUID_TYPE = PG_UUID(as_uuid=True)

metadata = MetaData(naming_convention={
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
})


class Base(DeclarativeBase):
    __abstract__: bool = True

    metadata = metadata

    # noinspection PyMethodParameters
    @declared_attr.directive
    def __tablename__(cls) -> str:
        return cls.__name__.lower()

    id: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, unique=True, primary_key=True, nullable=False, default=uuid6.uuid7)
    begins: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ends: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return "<{klass} @{id:x} {attrs}>".format(
            klass=self.__class__.__name__,
            id=id(self) & 0xFFFFFF,
            attrs=" ".join("{}={!r}".format(k, v) for k, v in self.__dict__.items()),
        )


class BaseCategory(Base):
    __abstract__: bool = True
    __unique_index__: bool = False
    __name_index__: bool = False
    __name_nullable__: bool = True

    category: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("category.id"))
    code: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String, index=__name_index__, nullable=__name_nullable__)
    creator: Mapped[Optional[uuid6.UUID]] = mapped_column(UUID_TYPE, ForeignKey("user.id"), index=True)

    # noinspection PyMethodParameters
    @declared_attr.directive
    def __table_args__(cls) -> tuple[Index]:
        return (
            Index(
                f"{cls.__name__.lower()}_category_code_idx",
                'category', 'code',
                unique=cls.__unique_index__
            ),
        )


class CrossTable(Base):
    __abstract__: bool = True

    table: Mapped[str] = mapped_column(String)
    objectid: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE) #access table (future)

    # noinspection PyMethodParameters
    @declared_attr.directive
    def __table_args__(cls) -> tuple[Index]:
        return (Index(f"{cls.__name__.lower()}_table_objectid_idx", 'table', 'objectid'),)


class DescriptionMixin:
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class User(Base):
    email: Mapped[Optional[str]] = mapped_column(String, index=True, unique=True, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String, index=True, unique=True, nullable=True)
    password: Mapped[str] = mapped_column(String)
    person: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("person.id"), index=True)
    validated: Mapped[bool] = mapped_column(Boolean, default=False)
    public_key: Mapped[str] = mapped_column(String)

    __table_args__ = (
        CheckConstraint(or_(email.is_not(None), phone.is_not(None))),
    )


class Category(BaseCategory, DescriptionMixin):
    value: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class Entity(BaseCategory, DescriptionMixin):
    value: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class Procedure(BaseCategory, CrossTable, DescriptionMixin):
    procedure: Mapped[str] = mapped_column(String)


class State(BaseCategory, CrossTable, DescriptionMixin):
    state: Mapped[str] = mapped_column(String)
    next: Mapped[Optional[List[uuid6.UUID]]] = mapped_column(ARRAY(UUID_TYPE), nullable=True)
    proc_in: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("procedure.id"), nullable=True)
    proc_out: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("procedure.id"), nullable=True)

    __table_args__ = (
        Index('state_main_idx', 'category', 'code', 'table', 'objectid'),
    )


class Relation(BaseCategory, CrossTable):
    related_table: Mapped[str] = mapped_column(String, nullable=False)
    related_id: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, nullable=False)

    __table_args__ = (
        Index('name_src_idx', 'category', 'code', 'table', 'objectid', 'related_table'),
        Index('name_trg_idx', 'category', 'code', 'related_table', 'related_id', 'table'),
    )


class Company(BaseCategory):
    country: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("country.id"))
    registered: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    closed: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)

    __table_args__ = (
        Index('company_name_idx', 'category', 'country', 'code', 'name'),
    )


class Property(BaseCategory, CrossTable):
    value: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    value_int: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    value_dec: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    value_dt: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index('property_main_idx',
              'table', 'category', 'code', 'objectid'
        ),
        Index('property_value_idx',
              'table', 'category', 'code', 'objectid', 'value'
        ),
        Index('property_value_int_idx',
              'table', 'category', 'code', 'objectid', 'value_int'
        ),
        Index('property_value_dec_idx',
              'table', 'category', 'code', 'objectid', 'value_dec'
        ),
        Index('property_value_dt_idx',
              'table', 'category', 'code', 'objectid', 'value_dt'
        ),
        CheckConstraint(or_(value.is_not(None),
                            value_int.is_not(None),
                            value_dec.is_not(None),
                            value_dt.is_not(None),
                        )
        )
    )


class Address(BaseCategory, CrossTable, DescriptionMixin):
    country: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("country.id"))
    region: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("place.id"))
    place: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("place.id"))
    postcode: Mapped[str] = mapped_column(String, nullable=True)
    position: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE)
    building: Mapped[str] = mapped_column(String)
    apartment: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index('address_idx', 'country', 'region', 'place', 'postcode', 'position'),
    )


class Country(Base, DescriptionMixin):
    iso2: Mapped[str] = mapped_column(String, index=True, unique=True)
    iso3: Mapped[str] = mapped_column(String, index=True, unique=True)
    m49: Mapped[int] = mapped_column(SMALLINT, index=True, nullable=True)
    name: Mapped[str] = mapped_column(String, index=True)
    creator: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("user.id"))


class LocationGEO(BaseCategory, CrossTable, DescriptionMixin):
    coordinates: Mapped[Geography] = mapped_column(Geography(geometry_type="POINT", srid=4326), index=True)


class Picture(BaseCategory, CrossTable, DescriptionMixin):
    picture: Mapped[bytes] = mapped_column(BYTEA)


class Currency(BaseCategory, DescriptionMixin):
    __unique_index__: bool = True

    num: Mapped[int] = mapped_column(SMALLINT, index=True, nullable=True)
    adjective: Mapped[str] = mapped_column(String)
    name_plural: Mapped[str] = mapped_column(String)
    name_minor: Mapped[str] = mapped_column(String)
    name_minor_plural: Mapped[str] = mapped_column(String)
    symbol: Mapped[str] = mapped_column(String)
    symbol_native: Mapped[str] = mapped_column(String)
    decimals: Mapped[int] = mapped_column(Integer)
    rounding: Mapped[float] = mapped_column(Numeric)

    __table_args__ = (
        Index('currency_code_idx', 'category', 'code', unique=True),
        Index('currency_num_idx', 'category', 'num', unique=True),
    )


class Account(BaseCategory, CrossTable, DescriptionMixin):
    currency: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("currency.id"))

    __table_args__ = (
        Index('account_issuer_idx', 'category', 'code', 'currency', 'table', 'objectid', unique=True),
    )


class Message(BaseCategory):
    receiver: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("user.id"))
    title: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(String)

    __table_args__ = (
        Index('message_idx', 'category', 'code', 'creator', 'receiver', 'begins'),
        Index('message_sender_idx', 'category', 'code', 'creator', 'begins'),
        Index('message_receiver_idx', 'category', 'code', 'receiver', 'begins'),
    )


class Operation(BaseCategory, DescriptionMixin):
    number: Mapped[str] = mapped_column(String)
    debit: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("account.id"))
    credit: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("account.id"))
    amount: Mapped[float] = mapped_column(Numeric)

    __table_args__ = (
        Index('operation_idx', 'category', 'code', 'debit', 'credit', 'begins'),
        Index('operation_db_idx', 'category', 'code', 'debit', 'number', 'begins'),
        Index('operation_cr_idx', 'category', 'code', 'credit', 'number', 'begins'),
    )


class Data(BaseCategory, CrossTable, DescriptionMixin):
    name: Mapped[str] = mapped_column(String)
    hash: Mapped[str] = mapped_column(String)
    algorithm: Mapped[str] = mapped_column(String)
    content: Mapped[bytes] = mapped_column(BYTEA)

    __table_args__ = (
        Index('data_idx', 'category', 'code', 'table', 'objectid', 'algorithm', 'hash'),
    )


class Document(BaseCategory, CrossTable, DescriptionMixin):
    country: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("country.id"))
    series: Mapped[str] = mapped_column(String)
    number: Mapped[str] = mapped_column(String)
    issue: Mapped[datetime.date] = mapped_column(Date, default=func.current_date(), nullable=False)
    expire: Mapped[datetime.date] = mapped_column(Date, nullable=True)
    content: Mapped[str] = mapped_column(String)

    __table_args__ = (
        Index('document_idx', 'category', 'code', 'country', 'series', 'number', 'issue'),
    )


class Place(BaseCategory, DescriptionMixin):
    country: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("country.id"), index=True)

    __table_args__ = (
        Index('place_name_idx', 'country', 'name'),
    )


class Person(Base):
    name_first: Mapped[str] = mapped_column(String, nullable=False)
    name_last: Mapped[str] = mapped_column(String, nullable=False)
    name_third: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sex: Mapped[bool] = mapped_column(Boolean)
    birthdate: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    birth_place: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("place.id"))

    __table_args__ = (
        Index(
            'person_idx', 'name_first', 'name_last', 'name_third', 'sex', 'birthdate', 'birth_place'
        ),
    )


class Rate(BaseCategory, CrossTable, DescriptionMixin):
    value: Mapped[float] = mapped_column(Numeric)


class Position(Base):
    rate: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("rate.id"), index=True)
    value: Mapped[float] = mapped_column(Numeric)


class Language(BaseCategory):
    iso: Mapped[str] = mapped_column(String, index=True)


class Translation(CrossTable):
    language: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("language.id"), index=True)
    text: Mapped[str] = mapped_column(String)


class Access(Base):
    user_in: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("user.id"), index=True)
    hash_out: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE)
    # пока думаю как реализовать возврат нужного UUID без хранения


class SensitiveData(BaseCategory, CrossTable):
    ...


class Signature(BaseCategory, CrossTable, DescriptionMixin):
    public_key: Mapped[str] = mapped_column(String)
