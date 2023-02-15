import uuid
from sqlalchemy import Column, String, ForeignKey, DateTime, Date, Index, Integer, Numeric
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID, BYTEA
from sqlalchemy.sql import func

Base = declarative_base()


class Entity(Base):
    __tablename__: str = 'entity'

    id = Column(UUID(as_uuid=True), unique=True, primary_key=True, nullable=False, default=uuid.uuid4)
    category = Column(String, ForeignKey("category.code"))
    code = Column(String)
    name = Column(String)
    value = Column(String)
    description = Column(String, nullable=True)
    begins = Column(DateTime(timezone=True), default=func.now())
    ends = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index('name_code_idx', 'category', 'code'),
    )

    def __repr__(self):
        return f'id={self.id}; category={self.category}; code={self.code}; name={self.name}'


class Category(Base):
    __tablename__: str = 'category'

    id = Column(UUID(as_uuid=True), unique=True, primary_key=True, nullable=False, default=uuid.uuid4)
    category = Column(String)
    code = Column(String)
    name = Column(String)
    value = Column(String)
    description = Column(String, nullable=True)
    begins = Column(DateTime(timezone=True), default=func.now())
    ends = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index('category_idx', 'category', 'code', unique=True),
    )

    def __repr__(self):
        return f'category={self.category}; code={self.code}; name={self.name}; value={self.value}'


class Status(Base):
    __tablename__: str = 'status'

    id = Column(UUID(as_uuid=True), unique=True, primary_key=True, nullable=False, default=uuid.uuid4)
    category = Column(String)
    code = Column(String)
    name = Column(String)
    value = Column(String)
    description = Column(String, nullable=True)
    begins = Column(DateTime(timezone=True), default=func.now())
    ends = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index('status_idx', 'category', 'code', unique=True),
    )

    def __repr__(self):
        return f'category={self.category}; code={self.code}; name={self.name}; value={self.value}'


class User(Base):
    __tablename__: str = 'user'

    id = Column(UUID(as_uuid=True), unique=True, primary_key=True, nullable=False, default=uuid.uuid4)
    username = Column(String, index=True, unique=True)
    passhash = Column(String)
    begins = Column(DateTime(timezone=True), default=func.now())
    ends = Column(DateTime(timezone=True), nullable=True)
    person_id = Column(UUID(as_uuid=True), ForeignKey("person.id"))

    def __repr__(self):
        return f'id={self.id}; name={self.username}'


class Relation(Base):
    __tablename__: str = 'relation'

    id = Column(UUID(as_uuid=True), unique=True, primary_key=True, nullable=False, default=uuid.uuid4)
    name = Column(String)
    src = Column(String)
    src_id = Column(UUID(as_uuid=True), nullable=False)
    trg = Column(String)
    trg_id = Column(UUID(as_uuid=True), nullable=False)
    begins = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    ends = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index('name_src_idx', 'name', 'src', 'trg', 'src_id', unique=True),
        Index('name_trg_idx', 'name', 'src', 'trg', 'trg_id', unique=True),
    )

    def __repr__(self):
        return f'id={self.id}; name={self.name}; \
                src={self.src}; src_id={self.src_id}; trg={self.trg}; trg_id={self.trg_id}'


class Person(Base):
    __tablename__: str = 'person'

    id = Column(UUID(as_uuid=True), unique=True, primary_key=True, nullable=False, default=uuid.uuid4)
    name_first = Column(String, nullable=False)
    name_last = Column(String, nullable=False)
    name_third = Column(String, nullable=True)
    birthdate = Column(Date, nullable=False)
    __table_args__ = (
        Index('name_birth_idx', 'name_first', 'name_last', 'name_third', 'birthdate'),
    )

    def __repr__(self):
        return f'id={self.id}; name={self.name_first}{self.name_third}{self.name_last}; birth={self.birthdate}'


class Company(Base):
    __tablename__: str = 'company'

    id = Column(UUID(as_uuid=True), unique=True, primary_key=True, nullable=False, default=uuid.uuid4)
    name = Column(String)
    country = Column(UUID(as_uuid=True), ForeignKey("country.id"))
    code = Column(String)
    begins = Column(Date, nullable=False)
    ends = Column(Date, nullable=True)
    __table_args__ = (
        Index('company_num_idx', 'country', 'code'),
    )

    def __repr__(self):
        return f'id={self.id}; name={self.name}; country={self.country}; code={self.code}'


class Property(Base):
    __tablename__: str = 'property'

    id = Column(UUID(as_uuid=True), unique=True, primary_key=True, nullable=False, default=uuid.uuid4)
    table = Column(String)
    object = Column(UUID(as_uuid=True), nullable=False)
    code = Column(String)
    name = Column(String)
    value = Column(String)
    value_int = Column(Integer)
    value_dec = Column(Numeric)
    value_dt = Column(DateTime(timezone=True))
    begins = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    ends = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index('obj_idx', 'table', 'name', 'object'),
        Index('val_idx', 'table', 'name', 'value'),
        Index('val_int_idx', 'table', 'name', 'value_int'),
        Index('val_dec_idx', 'table', 'name', 'value_dec'),
        Index('val_dt_idx', 'table', 'name', 'value_dt'),
    )

    def __repr__(self):
        return f'id={self.id}; table={self.table}; name={self.name}; object={self.object}; \
                value={self.value | self.value_int | self.value_dec | self.value_dt}'


class Location(Base):
    __tablename__: str = 'location'

    id = Column(UUID(as_uuid=True), unique=True, primary_key=True, nullable=False, default=uuid.uuid4)
    country = Column(UUID(as_uuid=True), ForeignKey("country.id"))
    region = Column(UUID(as_uuid=True))
    area = Column(UUID(as_uuid=True))
    area_type = Column(UUID(as_uuid=True))
    zip = Column(String)
    street = Column(UUID(as_uuid=True))
    building = Column(String)
    apartment = Column(String)
    begins = Column(Date, default=func.current_date(), nullable=False)
    ends = Column(Date, nullable=True)
    __table_args__ = (
        Index('address_idx', 'country', 'region', 'area', 'area_type', 'zip', 'street'),
    )

    def __repr__(self):
        return f'id={self.id}'


class Country(Base):
    __tablename__: str = 'country'

    id = Column(UUID(as_uuid=True), unique=True, primary_key=True, nullable=False, default=uuid.uuid4)
    code = Column(String, index=True)
    name = Column(String)
    currency = Column(UUID(as_uuid=True), ForeignKey("currency.id"))
    description = Column(String, nullable=True)
    begins = Column(DateTime(timezone=True), default=func.now())
    ends = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f'id={self.id}; code={self.code}; name={self.name}'


class Currency(Base):
    __tablename__: str = 'currency'

    id = Column(UUID(as_uuid=True), unique=True, primary_key=True, nullable=False, default=uuid.uuid4)
    code = Column(String, index=True)
    type = Column(String, index=True)
    name = Column(String)
    description = Column(String, nullable=True)
    begins = Column(DateTime(timezone=True), default=func.now())
    ends = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f'id={self.id}; code={self.code}; name={self.name}; type={self.type}'


class Account(Base):
    __tablename__: str = 'account'

    id = Column(UUID(as_uuid=True), unique=True, primary_key=True, nullable=False, default=uuid.uuid4)
    table = Column(String)
    code = Column(String, index=True)
    name = Column(String)
    currency = Column(UUID(as_uuid=True), ForeignKey("currency.id"))
    description = Column(String, nullable=True)
    begins = Column(DateTime(timezone=True), default=func.now())
    ends = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f'id={self.id}; code={self.code}; name={self.name}'


class Message(Base):
    __tablename__: str = 'message'

    id = Column(UUID(as_uuid=True), unique=True, primary_key=True, nullable=False, default=uuid.uuid4)
    code = Column(UUID(as_uuid=True), ForeignKey("category.id"))
    name = Column(String)
    sender = Column(UUID(as_uuid=True), ForeignKey("person.id"))
    receiver = Column(UUID(as_uuid=True), ForeignKey("person.id"))
    description = Column(String, nullable=True)
    content = Column(String, nullable=True)
    begins = Column(DateTime(timezone=True), default=func.now())
    ends = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f'id={self.id}; code={self.code}; name={self.name}; sender={self.sender}; receiver={self.receiver}'


class Operation(Base):
    __tablename__: str = 'operation'

    id = Column(UUID(as_uuid=True), unique=True, primary_key=True, nullable=False, default=uuid.uuid4)
    code = Column(UUID(as_uuid=True), ForeignKey("category.id"))
    number = Column(String)
    debit = Column(UUID(as_uuid=True), ForeignKey("account.id"))
    credit = Column(UUID(as_uuid=True), ForeignKey("account.id"))
    amount = Column(Numeric)
    description = Column(String, nullable=True)
    begins = Column(DateTime(timezone=True), default=func.now())
    ends = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index('operation_idx', 'code', 'debit', 'credit', 'begins'),
        Index('operation_db_idx', 'code', 'debit', 'number', 'begins'),
        Index('operation_cr_idx', 'code', 'credit', 'number', 'begins'),
    )

    def __repr__(self):
        return f'id={self.id}; code={self.code}; debit={self.debit}; credit={self.credit}; amount={self.amount}'


class Data(Base):
    __tablename__: str = 'data'

    id = Column(UUID(as_uuid=True), unique=True, primary_key=True, nullable=False, default=uuid.uuid4)
    table = Column(String)
    object = Column(UUID(as_uuid=True), nullable=False)
    code = Column(String)
    name = Column(String)
    hash = Column(String, index=True)
    algorithm = Column(String)
    content = Column(BYTEA)
    description = Column(String, nullable=True)
    begins = Column(DateTime(timezone=True), default=func.now())
    ends = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index('data_object_idx', 'table', 'object', 'code', 'algorithm', 'hash'),
    )

    def __repr__(self):
        return f'id={self.id}; table={self.table}; object={self.object}; code={self.code}; name={self.name}'
