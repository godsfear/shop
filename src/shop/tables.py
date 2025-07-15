from geoalchemy2 import Geography
import datetime
import uuid6

from sqlalchemy.dialects.postgresql import UUID as PG_UUID, BYTEA, SMALLINT, ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, declared_attr, Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy import (String,
                        ForeignKey,
                        DateTime,
                        Date,
                        Index,
                        Integer,
                        Numeric,
                        Boolean,
                        MetaData)

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

    id: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE,
                                           unique=True,
                                           primary_key=True,
                                           nullable=False,
                                           default=uuid6.uuid7)
    begins: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    ends: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    def __repr__(self) -> str:
        return "<{klass} @{id:x} {attrs}>".format(
            klass=self.__class__.__name__,
            id=id(self) & 0xFFFFFF,
            attrs=" ".join("{}={!r}".format(k, v) for k, v in self.__dict__.items()),
        )


class BaseCategory(Base):
    __abstract__: bool = True
    __unique_index__: bool = False
    __name_nullable__: bool = True

    category: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("category.id"))
    code: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String, nullable=__name_nullable__)
    creator: Mapped[uuid6.UUID | None] = mapped_column(UUID_TYPE, ForeignKey("user.id"), index=True)

    # noinspection PyMethodParameters
    @declared_attr.directive
    def __table_args__(cls) -> tuple[Index]:
        return (
            Index(
                f"ix_{cls.__name__.lower()}_category_code",
                'category', 'code',
                unique=cls.__unique_index__
            ),
        )


class CrossTable(Base):
    __abstract__: bool = True

    table: Mapped[str] = mapped_column(String)
    objectid: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE)

    # noinspection PyMethodParameters
    @declared_attr.directive
    def __table_args__(cls) -> tuple[Index]:
        return (Index(f"ix_{cls.__name__.lower()}_table_objectid", 'table', 'objectid'),)


class DescriptionMixin:
    description: Mapped[str | None] = mapped_column(String, nullable=True)


class User(Base):
    contact: Mapped[dict] = mapped_column(JSONB)
    password_hash: Mapped[str] = mapped_column(String)
    person: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("person.id"), index=True)
    validated: Mapped[bool] = mapped_column(Boolean, default=False)
    public_key: Mapped[str] = mapped_column(String)

    __table_args__ = ( # type: ignore
        Index('ix_user_contact', 'contact', postgresql_using='gin'),
    )


class Category(BaseCategory, DescriptionMixin):
    value: Mapped[dict] = mapped_column(JSONB, nullable=True)
    __table_args__ = ( # type: ignore
        Index('ix_category_value','category', 'code', 'value', postgresql_using='gin'),
    )


class Entity(BaseCategory, CrossTable, DescriptionMixin):
    value: Mapped[dict] = mapped_column(JSONB, nullable=True)


class Procedure(BaseCategory, CrossTable, DescriptionMixin):
    procedure: Mapped[str] = mapped_column(String)


class State(BaseCategory, CrossTable, DescriptionMixin):
    state: Mapped[str] = mapped_column(String)
    next: Mapped[list[uuid6.UUID] | None] = mapped_column(ARRAY(UUID_TYPE), nullable=True)
    proc_in: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("procedure.id"), nullable=True)
    proc_out: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("procedure.id"), nullable=True)

    __table_args__ = ( # type: ignore
        Index('ix_state_main', 'category', 'code', 'table', 'objectid'),
    )


class Relation(BaseCategory, CrossTable, DescriptionMixin):
    related_table: Mapped[str] = mapped_column(String, nullable=False)
    related_id: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, nullable=False)

    __table_args__ = ( # type: ignore
        Index('ix_name_src', 'category', 'code', 'table', 'objectid', 'related_table'),
        Index('ix_name_trg', 'category', 'code', 'table', 'related_table', 'related_id'),
    )


class Company(BaseCategory):
    country: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("country.id"))
    registered: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    closed: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)

    __table_args__ = ( # type: ignore
        Index('ix_company_name', 'category', 'country', 'code', 'name'),
    )


class Property(BaseCategory, CrossTable, DescriptionMixin):
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)

    __table_args__ = ( # type: ignore
        Index('ix_property_main',
              'table', 'category', 'code', 'objectid'
        ),
        Index('ix_property_value',
              'table', 'category', 'code', 'objectid', 'value', postgresql_using='gin'
        ),
    )


class Address(BaseCategory, CrossTable, DescriptionMixin):
    country: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("country.id"))
    region: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("place.id"))
    place: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("place.id"))
    location: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("place.id"))
    building: Mapped[str] = mapped_column(String)
    apartment: Mapped[str | None] = mapped_column(String, nullable=True)
    postcode: Mapped[str] = mapped_column(String, nullable=True)
    geo: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("GEO.id"))

    __table_args__ = ( # type: ignore
        Index('ix_address', 'country', 'region', 'place', 'postcode', 'position'),
    )


class Country(Base, DescriptionMixin):
    iso2: Mapped[str] = mapped_column(String, index=True, unique=True)
    iso3: Mapped[str] = mapped_column(String, index=True, unique=True)
    m49: Mapped[int] = mapped_column(SMALLINT, index=True, nullable=True)
    name: Mapped[str] = mapped_column(String, index=True)
    creator: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("user.id"))


class GEO(BaseCategory, CrossTable, DescriptionMixin):
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

    __table_args__ = ( # type: ignore
        Index('uq_currency_code', 'category', 'code', unique=True),
        Index('uq_currency_num', 'category', 'num', unique=True),
    )


class Account(BaseCategory, CrossTable, DescriptionMixin):
    currency: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("currency.id"))

    __table_args__ = ( # type: ignore
        Index('uq_account_issuer', 'category', 'code', 'currency', 'table', 'objectid', unique=True),
    )


class Balance(Base):
    rate: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("account.id"), index=True)
    value: Mapped[float] = mapped_column(Numeric)


class Message(BaseCategory):
    receiver: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("user.id"))
    title: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(String)

    __table_args__ = ( # type: ignore
        Index('ix_message', 'category', 'code', 'creator', 'receiver', 'begins'),
        Index('ix_message_sender', 'category', 'code', 'creator', 'begins'),
        Index('ix_message_receiver', 'category', 'code', 'receiver', 'begins'),
    )


class Operation(BaseCategory, DescriptionMixin):
    number: Mapped[str] = mapped_column(String)
    debit: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("account.id"))
    credit: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("account.id"))
    amount: Mapped[float] = mapped_column(Numeric)

    __table_args__ = ( # type: ignore
        Index('ix_operation', 'category', 'code', 'debit', 'credit', 'begins'),
        Index('ix_operation_db', 'category', 'code', 'debit', 'number', 'begins'),
        Index('ix_operation_cr', 'category', 'code', 'credit', 'number', 'begins'),
    )


class Data(BaseCategory, CrossTable, DescriptionMixin):
    name: Mapped[str] = mapped_column(String)
    hash: Mapped[str] = mapped_column(String)
    algorithm: Mapped[str] = mapped_column(String)
    content: Mapped[bytes] = mapped_column(BYTEA)

    __table_args__ = ( # type: ignore
        Index('ix_data', 'category', 'code', 'table', 'objectid', 'algorithm', 'hash'),
    )


class Document(BaseCategory, CrossTable, DescriptionMixin):
    country: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("country.id"))
    series: Mapped[str] = mapped_column(String)
    number: Mapped[str] = mapped_column(String)
    issue: Mapped[datetime.date] = mapped_column(Date, default=func.current_date(), nullable=False)
    expire: Mapped[datetime.date] = mapped_column(Date, nullable=True)
    content: Mapped[str] = mapped_column(String)

    __table_args__ = ( # type: ignore
        Index('ix_document', 'category', 'code', 'country', 'series', 'number', 'issue'),
    )


class Place(BaseCategory, DescriptionMixin):
    country: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("country.id"), index=True)

    __table_args__ = ( # type: ignore
        Index('ix_place_name', 'country', 'name'),
    )


class Person(Base):
    name: Mapped[dict] = mapped_column(JSONB)
    sex: Mapped[bool] = mapped_column(Boolean)
    birthdate: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    birth_place: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("place.id"))
    sensitive: Mapped[list[str]] = mapped_column(ARRAY(String),nullable=True)

    __table_args__ = ( # type: ignore
        Index('ix_person',
              'name', 'sex', 'birthdate', 'birth_place', postgresql_using='gin')
    )


class Language(BaseCategory):
    iso: Mapped[str] = mapped_column(String, index=True)


class Translation(CrossTable):
    text: Mapped[dict] = mapped_column(JSONB)


class Access(Base):
    user_in: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("user.id"), index=True)
    hash_out: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE)
    # пока думаю как реализовать возврат нужного UUID без хранения
