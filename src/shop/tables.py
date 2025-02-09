import datetime
import uuid

from typing import List
from sqlalchemy import String, ForeignKey, DateTime, Date, Index, Integer, Numeric, Boolean, CheckConstraint, MetaData
from sqlalchemy.dialects.postgresql import UUID, BYTEA, SMALLINT, ARRAY
from sqlalchemy.orm import DeclarativeBase, declared_attr, Mapped, mapped_column
from sqlalchemy.sql import func


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

    id: Mapped[uuid.UUID] = mapped_column(unique=True, primary_key=True, nullable=False, default=uuid.uuid4)
    begins: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    ends: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return "<{klass} @{id:x} {attrs}>".format(
            klass=self.__class__.__name__,
            id=id(self) & 0xFFFFFF,
            attrs=" ".join("{}={!r}".format(k, v) for k, v in self.__dict__.items()),
        )


class BaseCategory(Base):
    __abstract__: bool = True
    __unique_index__: bool = False

    category: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("category.id"))
    code: Mapped[str] = mapped_column(String)
    user: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), index=True)

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
    objectid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))

    # noinspection PyMethodParameters
    @declared_attr.directive
    def __table_args__(cls) -> tuple[Index]:
        return (Index(f"{cls.__name__.lower()}_table_objectid_idx", 'table', 'objectid'),)


class Description:
    description: Mapped[str | None] = mapped_column(String, nullable=True)


class User(Base):
    email: Mapped[str | None] = mapped_column(String, index=True, unique=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, index=True, unique=True, nullable=True)
    password: Mapped[str] = mapped_column(String)
    person: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("person.id"), index=True)
    validated: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        CheckConstraint('NOT(email IS NULL AND phone IS NULL)'),
    )


class Category(Base, Description):
    category: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    code: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    value: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index('category_idx', 'category', 'code'),
    )


class Entity(BaseCategory, Description):
    name: Mapped[str] = mapped_column(String)
    value: Mapped[str | None] = mapped_column(String, nullable=True)


class Procedure(BaseCategory, CrossTable, Description):
    name: Mapped[str] = mapped_column(String, index=True)
    procedure: Mapped[str] = mapped_column(String)


class State(BaseCategory, CrossTable, Description):
    state: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    next: Mapped[List[str] | None] = mapped_column(ARRAY(String), nullable=True)
    proc_in: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("procedure.id"), nullable=True)
    proc_out: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("procedure.id"), nullable=True)

    __table_args__ = (
        Index('state_idx', 'category', 'code', 'state'),
        Index('state_objectid_idx', 'table', 'objectid', 'category', 'code', 'state', unique=True),
    )


class Relation(BaseCategory):
    name: Mapped[str] = mapped_column(String)
    src: Mapped[str] = mapped_column(String)
    src_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    trg: Mapped[str] = mapped_column(String)
    trg_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    __table_args__ = (
        Index('name_src_idx', 'category', 'code', 'src', 'trg', 'src_id'),
        Index('name_trg_idx', 'category', 'code', 'src', 'trg', 'trg_id'),
    )


class Company(BaseCategory):
    name: Mapped[str] = mapped_column(String)
    country: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("country.id"))
    registered: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    closed: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        Index('company_name_idx', 'category', 'country', 'code', 'name'),
    )


class Property(BaseCategory, CrossTable):
    name: Mapped[str] = mapped_column(String)
    value: Mapped[str | None] = mapped_column(String, nullable=True)
    value_int: Mapped[int | None] = mapped_column(Integer, nullable=True)
    value_dec: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    value_dt: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index('obj_idx', 'table', 'category', 'code', 'objectid'),
        Index('val_idx', 'table', 'category', 'code', 'value'),
        Index('val_int_idx', 'table', 'category', 'code', 'value_int'),
        Index('val_dec_idx', 'table', 'category', 'code', 'value_dec'),
        Index('val_dt_idx', 'table', 'category', 'code', 'value_dt'),
        CheckConstraint('NOT(value IS NULL AND value_int IS NULL AND value_dec IS NULL AND value_dt IS NULL)'),
    )


class Address(BaseCategory):
    country: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("country.id"))
    region: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("place.id"))
    place: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("place.id"))
    postcode: Mapped[str] = mapped_column(String, nullable=True)
    position: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    building: Mapped[str] = mapped_column(String)
    apartment: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index('address_idx', 'country', 'region', 'place', 'postcode', 'position'),
    )


class Country(Base, Description):
    iso2: Mapped[str] = mapped_column(String, index=True, unique=True)
    iso3: Mapped[str] = mapped_column(String, index=True, unique=True)
    m49: Mapped[int] = mapped_column(SMALLINT, index=True, nullable=True)
    name: Mapped[str] = mapped_column(String, index=True)
    user: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"))


class Picture(BaseCategory, CrossTable, Description):
    picture: Mapped[bytes] = mapped_column(BYTEA)


class Currency(BaseCategory, Description):
    __unique_index__: bool = True

    num: Mapped[int] = mapped_column(SMALLINT, index=True, nullable=False)
    adjective: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    name_plural: Mapped[str] = mapped_column(String)
    name_minor: Mapped[str] = mapped_column(String)
    name_minor_plural: Mapped[str] = mapped_column(String)
    symbol: Mapped[str] = mapped_column(String)
    symbol_native: Mapped[str] = mapped_column(String)
    decimals: Mapped[int] = mapped_column(Integer)
    rounding: Mapped[float] = mapped_column(Numeric)

    __table_args__ = (
        Index('currency_num_idx', 'category', 'num'),
    )


class Account(BaseCategory, CrossTable, Description):
    currency: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("currency.id"))
    name: Mapped[str] = mapped_column(String)

    __table_args__ = (
        Index('account_issuer_idx', 'category', 'code', 'currency', 'table', 'objectid', unique=True),
    )


class Message(BaseCategory):
    name: Mapped[str] = mapped_column(String)
    receiver: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"))
    title: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(String)

    __table_args__ = (
        Index('message_idx', 'category', 'code', 'user', 'receiver', 'begins'),
        Index('message_sender_idx', 'category', 'code', 'user', 'begins'),
        Index('message_receiver_idx', 'category', 'code', 'receiver', 'begins'),
    )


class Operation(BaseCategory, Description):
    number: Mapped[str] = mapped_column(String)
    debit: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("account.id"))
    credit: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("account.id"))
    amount: Mapped[float] = mapped_column(Numeric)

    __table_args__ = (
        Index('operation_idx', 'category', 'code', 'debit', 'credit', 'begins'),
        Index('operation_db_idx', 'category', 'code', 'debit', 'number', 'begins'),
        Index('operation_cr_idx', 'category', 'code', 'credit', 'number', 'begins'),
    )


class Data(BaseCategory, CrossTable, Description):
    name: Mapped[str] = mapped_column(String)
    hash: Mapped[str] = mapped_column(String)
    algorithm: Mapped[str] = mapped_column(String)
    content: Mapped[bytes] = mapped_column(BYTEA)

    __table_args__ = (
        Index('data_idx', 'category', 'code', 'table', 'objectid', 'algorithm', 'hash'),
    )


class Document(BaseCategory, CrossTable, Description):
    country: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("country.id"))
    name: Mapped[str] = mapped_column(String)
    series: Mapped[str] = mapped_column(String)
    number: Mapped[str] = mapped_column(String)
    issue: Mapped[datetime.date] = mapped_column(Date, default=func.current_date(), nullable=False)
    expire: Mapped[datetime.date] = mapped_column(Date, nullable=True)

    __table_args__ = (
        Index('document_idx', 'category', 'code', 'country', 'series', 'number', 'issue'),
    )


class Place(BaseCategory, Description):
    country: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("country.id"), index=True)
    name: Mapped[str] = mapped_column(String)

    __table_args__ = (
        Index('place_name_idx', 'country', 'name'),
    )


class Person(Base):
    name_first: Mapped[str] = mapped_column(String, nullable=False)
    name_last: Mapped[str] = mapped_column(String, nullable=False)
    name_third: Mapped[str | None] = mapped_column(String, nullable=True)
    sex: Mapped[bool] = mapped_column(Boolean)
    birthdate: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    birth_place: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("place.id"))

    __table_args__ = (
        Index(
            'person_idx', 'name_first', 'name_last', 'name_third', 'sex', 'birthdate', 'birth_place'
        ),
    )


class Rate(BaseCategory, CrossTable, Description):
    name: Mapped[str] = mapped_column(String)
    value: Mapped[float] = mapped_column(Numeric)


class Position(Base):
    rate: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rate.id"), index=True)
    value: Mapped[float] = mapped_column(Numeric)


class Language(BaseCategory):
    iso: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String, index=True)


class Translation(CrossTable):
    language: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("language.id"), index=True)
    text: Mapped[str] = mapped_column(String)


class Access(BaseCategory, CrossTable):
    ...
