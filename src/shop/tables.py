from geoalchemy2 import Geography
import datetime
import enum
import uuid
import uuid6

from sqlalchemy.dialects.postgresql import UUID as PG_UUID, BYTEA, SMALLINT, ARRAY, JSONB
from sqlalchemy.orm import (DeclarativeBase,
                            ORMExecuteState,
                            Session,
                            declared_attr,
                            Mapped,
                            mapped_column,
                            with_loader_criteria)
from sqlalchemy.sql import func
from sqlalchemy import (String,
                        ForeignKey,
                        ForeignKeyConstraint,
                        DateTime,
                        Date,
                        Index,
                        Integer,
                        Numeric,
                        Boolean,
                        MetaData,
                        UniqueConstraint,
                        CheckConstraint,
                        event,
                        select,
                        text)

# частичные индексы "только активные записи" — см. автофильтр ниже
ACTIVE = text("ends IS NULL")


class Domain(enum.StrEnum):
    """Домены разделения данных (см. память проекта: псевдонимизация).

    identity    — идентифицирует персону/компанию; доступ строго ограничен;
    operational — рабочие данные на псевдонимах; доступны статистике;
    reference   — общие справочники.

    Единственная связь identity <-> operational — мост (Link), никогда прямые ссылки.
    """
    IDENTITY = 'identity'
    OPERATIONAL = 'operational'
    REFERENCE = 'reference'


def category_code_index(table: str, unique: bool = False) -> Index:
    """Типовой индекс справочной выборки (category, code) по активным записям."""
    prefix = 'uq' if unique else 'ix'
    return Index(f'{prefix}_{table}_category_code', 'category', 'code',
                 unique=unique, postgresql_where=ACTIVE)

UUID_TYPE = PG_UUID(as_uuid=True)

metadata = MetaData(naming_convention={
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
})


class Root(DeclarativeBase):
    """Технический корень: только общие metadata, никаких колонок.
    Для служебных таблиц вне темпоральной модели (реестр объектов)."""
    metadata = metadata


class Base(Root):
    __abstract__: bool = True

    # домен объекта в реестре; CrossTable-наследники домен не объявляют —
    # он наследуется от объекта-цели при регистрации (см. _register_new_objects)
    __domain__: Domain = Domain.REFERENCE

    # noinspection PyMethodParameters
    @declared_attr.directive
    def __tablename__(cls) -> str:
        return cls.__name__.lower()

    # noinspection PyMethodParameters
    @declared_attr.directive
    def __table_args__(cls) -> tuple:
        """Единая точка сборки table_args: автоматика + __local_table_args__.

        Автоматика только там, где забывчивость опасна: каждая CrossTable-таблица
        получает составной FK (objectid, table) -> object(id, table) — БД проверяет
        существование И тип цели полиморфной ссылки — плюс индекс (table, objectid).

        Свои индексы/констрейнты таблица объявляет в __local_table_args__
        (обычный кортеж, как __table_args__): он ДОПОЛНЯЕТ автоматическую часть,
        а не затирает её, как затирало бы переопределение __table_args__.
        """
        t = cls.__name__.lower()
        args: list = []
        if issubclass(cls, CrossTable):
            args.append(ForeignKeyConstraint(['objectid', 'table'],
                                             ['object.id', 'object.table']))
            args.append(Index(f'ix_{t}_table_objectid', 'table', 'objectid'))
        args.extend(cls.__dict__.get('__local_table_args__', ()))
        return tuple(args)

    id: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE,
                                           unique=True,
                                           primary_key=True,
                                           nullable=False,
                                           default=uuid6.uuid7)
    begins: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    ends: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    # копия-версия строки (см. versioning.py): строка с данным id — всегда
    # текущая версия (ссылки не ломаются), история — копии с version_of -> id;
    # копии закрыты (ends), скрыты автофильтром и НЕ регистрируются в реестре
    # noinspection PyMethodParameters
    @declared_attr
    def version_of(cls) -> Mapped[uuid6.UUID | None]:
        return mapped_column(UUID_TYPE, ForeignKey(f'{cls.__name__.lower()}.id'),
                             nullable=True, index=True)

    def __repr__(self) -> str:
        return "<{klass} @{id:x} {attrs}>".format(
            klass=self.__class__.__name__,
            id=id(self) & 0xFFFFFF,
            attrs=" ".join("{}={!r}".format(k, v) for k, v in self.__dict__.items()),
        )


class ObjectRegistry(Root):
    """Единый реестр объектов: каждая строка каждой Base-таблицы регистрируется
    здесь той же транзакцией (см. _register_new_objects). Полиморфные ссылки
    (CrossTable.objectid) получают за счёт этого настоящий FK.

    Намеренно НЕ наследует Base: у реестра нет begins/ends и собственной
    генерации id — id копируется из строки-владельца, временных меток нет,
    чтобы реестр не давал коррелировать моменты создания объектов.
    """
    __tablename__ = "object"

    id: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, primary_key=True)
    table: Mapped[str] = mapped_column(String)
    domain: Mapped[str] = mapped_column(String)

    __table_args__ = (
        # цель составного FK (objectid, table) — проверка типа ссылки
        UniqueConstraint('id', 'table', name='uq_object_id_table'),
        # домен ограничен и на уровне БД, а не только кода
        CheckConstraint(
            "domain IN ({})".format(', '.join(f"'{d.value}'" for d in Domain)),
            name='domain_valid',
        ),
    )


class Outbox(Root):
    """Transactional outbox (память проекта: queue-architecture).

    Событие пишется той же транзакцией, что и доменные данные (см. outbox.emit),
    консумер разбирает по FOR UPDATE SKIP LOCKED — очередь в Postgres,
    exactly-once в пределах БД. Отравленные события после N попыток
    помечаются processed + error и не блокируют очередь.
    """
    __tablename__ = "outbox"

    id: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid6.uuid7)
    topic: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSONB)
    created: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True),
                                                       server_default=func.now())
    processed: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True),
                                                                nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, server_default=text('0'))
    error: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index('ix_outbox_pending', 'created', postgresql_where=text('processed IS NULL')),
    )


class DomainBoundaryError(Exception):
    """Попытка связать объекты разных доменов минуя мост псевдонимизации."""


def _default_id(obj: 'Base'):
    """Генерирует id по default-колонке класса (uuid7, у Pseudonym — uuid4)."""
    d = type(obj).__table__.c.id.default
    if d is not None and d.is_callable:
        try:
            return d.arg(None)  # SQLAlchemy оборачивает callable с параметром context
        except TypeError:
            return d.arg()
    return uuid6.uuid7()


@event.listens_for(Session, "before_flush")
def _register_new_objects(session: Session, flush_context, instances) -> None:
    """Каждый новый Base-объект попадает в реестр object в той же транзакции.

    Домены: у якорных таблиц — из атрибута класса __domain__; у CrossTable-строк
    домен наследуется от объекта-цели (данные, прикреплённые к личности, сами
    становятся личными). Здесь же охраняется граница доменов: Relation не может
    связать объекты разных доменов — для этого существует только мост (Link).

    Работает только для ORM-пути (session.add). Сырые Core-insert'ы реестр
    не пополняют — при появлении таких путей записи нужны DB-триггеры.
    Копии-версии (version_of, см. versioning.py) не регистрируются:
    объект в реестре один, сколько бы версий у него ни было.
    """
    new_objs = [o for o in session.new
                if isinstance(o, Base) and o.version_of is None]
    if not new_objs:
        return
    for obj in new_objs:
        if obj.id is None:
            obj.id = _default_id(obj)

    domains: dict = {}          # id -> домен (создаваемые в этом flush)
    cross: list[CrossTable] = []
    for obj in new_objs:
        if isinstance(obj, CrossTable):
            cross.append(obj)
        else:
            d = type(obj).__domain__
            if d not in Domain:
                raise DomainBoundaryError(
                    f"{type(obj).__name__}.__domain__ = {d!r} — не входит в Domain")
            domains[obj.id] = d

    # цели, которых нет среди создаваемых, ищем в реестре
    wanted = {o.objectid for o in cross}
    wanted |= {o.related_id for o in cross if isinstance(o, Relation)}
    unknown = {t for t in wanted if t not in domains}
    if unknown:
        with session.no_autoflush:
            rows = session.execute(
                select(ObjectRegistry.id, ObjectRegistry.domain)
                .where(ObjectRegistry.id.in_(unknown))
            ).all()
        domains.update({r[0]: r[1] for r in rows})

    # CrossTable-строки могут цепляться друг к другу в одном flush — до неподвижной точки
    remaining = list(cross)
    while remaining:
        progressed = False
        for o in list(remaining):
            d = domains.get(o.objectid)
            if d is not None:
                domains[o.id] = d
                remaining.remove(o)
                progressed = True
        if not progressed:
            missing = sorted(str(o.objectid) for o in remaining)
            raise DomainBoundaryError(f'объекты-цели не найдены в реестре: {missing}')

    # мост крепится только к identity-объекту (персона, компания)
    for o in cross:
        if isinstance(o, Link) and domains[o.id] != Domain.IDENTITY:
            raise DomainBoundaryError(
                f"мост (Link) крепится только к identity-объекту, "
                f"цель '{o.table}' — домен '{domains[o.id]}'")

    # граница доменов: связь между доменами — только через мост
    for o in cross:
        if isinstance(o, Relation):
            d_src, d_trg = domains.get(o.objectid), domains.get(o.related_id)
            if d_trg is None:
                raise DomainBoundaryError(f'цель связи не найдена в реестре: {o.related_id}')
            if d_src != d_trg:
                raise DomainBoundaryError(
                    f"связь между доменами '{d_src}' и '{d_trg}' запрещена — только через мост")

    for obj in new_objs:
        session.add(ObjectRegistry(id=obj.id, table=obj.__tablename__,
                                   domain=domains[obj.id]))


@event.listens_for(Session, "do_orm_execute")
def _filter_expired(execute_state: ORMExecuteState) -> None:
    """Автофильтр темпоральной модели: каждый ORM-select видит только
    активные записи (ends IS NULL) по всем таблицам запроса.

    Историю запрашивать явно:
        session.execute(query.execution_options(include_expired=True))
    """
    if (
        execute_state.is_select
        and not execute_state.is_column_load
        and not execute_state.is_relationship_load
        and not execute_state.execution_options.get("include_expired", False)
    ):
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(Base, lambda cls: cls.ends.is_(None), include_aliases=True)
        )


class BaseCategory(Base):
    __abstract__: bool = True

    # nullable: корневые категории не имеют родителя, иначе первую строку не вставить
    category: Mapped[uuid6.UUID | None] = mapped_column(UUID_TYPE, ForeignKey("category.id"), nullable=True)
    code: Mapped[str] = mapped_column(String)
    # обязательность name — правило API (Create-модели), а не хранения;
    # уникальность (category, code) при необходимости объявляется в __table_args__ наследника
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    # use_alter: рёбра creator -> user замыкают цикл таблиц
    # (user -> person -> place -> category/country -> user), FK добавляется через ALTER
    creator: Mapped[uuid6.UUID | None] = mapped_column(UUID_TYPE,
                                                       ForeignKey("user.id", use_alter=True),
                                                       index=True)


class CrossTable(Base):
    """Полиморфная ссылка (table, objectid); составной FK на реестр
    и индекс добавляются автоматически — см. Base.__table_args__."""
    __abstract__: bool = True

    table: Mapped[str] = mapped_column(String)
    objectid: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE)


class DescriptionMixin:
    description: Mapped[str | None] = mapped_column(String, nullable=True)


class User(Base):
    __domain__ = Domain.IDENTITY

    contact: Mapped[dict] = mapped_column(JSONB)
    password_hash: Mapped[str] = mapped_column(String)
    person: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("person.id"), index=True)
    validated: Mapped[bool] = mapped_column(Boolean, default=False)
    public_key: Mapped[str] = mapped_column(String)
    # роли попадают в JWT (claims: sub + roles); выдача — только админом
    roles: Mapped[list[str]] = mapped_column(ARRAY(String), server_default=text("'{}'"))

    __local_table_args__ = (
        Index('ix_user_contact', 'contact', postgresql_using='gin', postgresql_where=ACTIVE),
    )


class Category(BaseCategory, DescriptionMixin):
    value: Mapped[dict] = mapped_column(JSONB, nullable=True)
    __local_table_args__ = (
        category_code_index('category'),
        Index('ix_category_value', 'value', postgresql_using='gin'),
    )


class Entity(BaseCategory, CrossTable, DescriptionMixin):
    value: Mapped[dict] = mapped_column(JSONB, nullable=True)
    __local_table_args__ = (category_code_index('entity'),)


class Relation(BaseCategory, CrossTable, DescriptionMixin):
    related_table: Mapped[str] = mapped_column(String, nullable=False)
    related_id: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, nullable=False)

    __local_table_args__ = (
        # вторая сторона связи проверяется так же, как первая (см. Base.__table_args__)
        ForeignKeyConstraint(['related_id', 'related_table'], ['object.id', 'object.table']),
        Index('ix_relation_src', 'category', 'code', 'table', 'objectid', 'related_table'),
        Index('ix_relation_trg', 'category', 'code', 'table', 'related_table', 'related_id'),
    )


class Company(BaseCategory):
    __domain__ = Domain.IDENTITY

    country: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("country.id"))
    registered: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    closed: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)

    __local_table_args__ = (
        Index('ix_company_name', 'category', 'country', 'code', 'name', postgresql_where=ACTIVE),
    )


class Property(BaseCategory, CrossTable, DescriptionMixin):
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)

    __local_table_args__ = (
        Index('ix_property_main',
              'table', 'category', 'code', 'objectid',
              postgresql_where=ACTIVE
        ),
        Index('ix_property_value', 'value', postgresql_using='gin'),
    )


class Address(BaseCategory, CrossTable, DescriptionMixin):
    country: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("country.id"))
    region: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("place.id"))
    place: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("place.id"))
    location: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("place.id"))
    building: Mapped[str] = mapped_column(String)
    apartment: Mapped[str | None] = mapped_column(String, nullable=True)
    postcode: Mapped[str] = mapped_column(String, nullable=True)
    geo: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("geo.id"))

    __local_table_args__ = (
        Index('ix_address', 'country', 'region', 'place', 'postcode', 'location',
              postgresql_where=ACTIVE),
    )


class Country(Base, DescriptionMixin):
    iso2: Mapped[str] = mapped_column(String, index=True, unique=True)
    iso3: Mapped[str] = mapped_column(String, index=True, unique=True)
    m49: Mapped[int] = mapped_column(SMALLINT, index=True, nullable=True)
    name: Mapped[str] = mapped_column(String, index=True)
    # nullable: страны сидируются до появления первого пользователя
    # (разрывает цикл user -> person -> place -> country -> user)
    creator: Mapped[uuid6.UUID | None] = mapped_column(UUID_TYPE,
                                                       ForeignKey("user.id", use_alter=True),
                                                       nullable=True)


class GEO(BaseCategory, CrossTable, DescriptionMixin):
    # geoalchemy2 сам создаёт пространственный GIST-индекс (idx_geo_coordinates)
    coordinates: Mapped[Geography] = mapped_column(Geography(geometry_type="POINT", srid=4326))
    __local_table_args__ = (category_code_index('geo'),)


class Picture(BaseCategory, CrossTable, DescriptionMixin):
    picture: Mapped[bytes] = mapped_column(BYTEA)
    __local_table_args__ = (category_code_index('picture'),)


class Currency(BaseCategory, DescriptionMixin):
    num: Mapped[int] = mapped_column(SMALLINT, index=True, nullable=True)
    adjective: Mapped[str] = mapped_column(String)
    name_plural: Mapped[str] = mapped_column(String)
    name_minor: Mapped[str] = mapped_column(String)
    name_minor_plural: Mapped[str] = mapped_column(String)
    symbol: Mapped[str] = mapped_column(String)
    symbol_native: Mapped[str] = mapped_column(String)
    decimals: Mapped[int] = mapped_column(Integer)
    rounding: Mapped[float] = mapped_column(Numeric)

    __local_table_args__ = (
        # уникальность — только среди активных: историческая версия валюты
        # с тем же кодом не мешает новой
        category_code_index('currency', unique=True),
        Index('uq_currency_num', 'category', 'num', unique=True, postgresql_where=ACTIVE),
    )


class Account(BaseCategory, CrossTable, DescriptionMixin):
    currency: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("currency.id"))

    __local_table_args__ = (
        Index('uq_account_issuer', 'category', 'code', 'currency', 'table', 'objectid',
              unique=True, postgresql_where=ACTIVE),
    )


class Balance(Base):
    __domain__ = Domain.OPERATIONAL

    rate: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("account.id"), index=True)
    value: Mapped[float] = mapped_column(Numeric)


class Message(BaseCategory):
    __domain__ = Domain.IDENTITY  # адресована конкретному пользователю

    receiver: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("user.id"))
    title: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(String)

    __local_table_args__ = (
        Index('ix_message', 'category', 'code', 'creator', 'receiver', 'begins'),
        Index('ix_message_sender', 'category', 'code', 'creator', 'begins'),
        Index('ix_message_receiver', 'category', 'code', 'receiver', 'begins'),
    )


class Operation(BaseCategory, DescriptionMixin):
    __domain__ = Domain.OPERATIONAL

    number: Mapped[str] = mapped_column(String)
    debit: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("account.id"))
    credit: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("account.id"))
    amount: Mapped[float] = mapped_column(Numeric)

    __local_table_args__ = (
        Index('ix_operation', 'category', 'code', 'debit', 'credit', 'begins'),
        Index('ix_operation_db', 'category', 'code', 'debit', 'number', 'begins'),
        Index('ix_operation_cr', 'category', 'code', 'credit', 'number', 'begins'),
    )


class Data(BaseCategory, CrossTable, DescriptionMixin):
    name: Mapped[str] = mapped_column(String)
    hash: Mapped[str] = mapped_column(String)
    algorithm: Mapped[str] = mapped_column(String)
    content: Mapped[bytes] = mapped_column(BYTEA)

    __local_table_args__ = (
        Index('ix_data', 'category', 'code', 'table', 'objectid', 'algorithm', 'hash'),
    )


class Document(BaseCategory, CrossTable, DescriptionMixin):
    country: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("country.id"))
    series: Mapped[str] = mapped_column(String)
    number: Mapped[str] = mapped_column(String)
    issue: Mapped[datetime.date] = mapped_column(Date, default=func.current_date(), nullable=False)
    expire: Mapped[datetime.date] = mapped_column(Date, nullable=True)
    content: Mapped[str] = mapped_column(String)

    __local_table_args__ = (
        Index('ix_document', 'category', 'code', 'country', 'series', 'number', 'issue'),
    )


class Place(BaseCategory, DescriptionMixin):
    country: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("country.id"), index=True)

    __local_table_args__ = (
        Index('ix_place_name', 'country', 'name', postgresql_where=ACTIVE),
    )


class Person(Base):
    __domain__ = Domain.IDENTITY

    name: Mapped[dict] = mapped_column(JSONB)
    sex: Mapped[bool] = mapped_column(Boolean)
    birthdate: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    birth_place: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("place.id"))
    sensitive: Mapped[list[str]] = mapped_column(ARRAY(String),nullable=True)

    __local_table_args__ = (
        Index('ix_person_name', 'name', postgresql_using='gin'),
        Index('ix_person_birthdate', 'birthdate'),
    )


class Language(BaseCategory):
    iso: Mapped[str] = mapped_column(String, index=True)
    __local_table_args__ = (category_code_index('language'),)


class Translation(CrossTable):
    text: Mapped[dict] = mapped_column(JSONB)


class Pseudonym(Base):
    """Обезличенный якорь операционного домена («пациент №...»).

    Никаких идентифицирующих полей. id — uuid4: uuid7 содержит время создания
    и позволил бы коррелировать псевдоним с персоной. По той же причине
    псевдонимы создаются пакетами заранее (см. PseudonymPool): begins псевдонима —
    это момент пополнения пула, а не момент создания моста.
    """
    __domain__ = Domain.OPERATIONAL

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)


class PseudonymPool(Root):
    """Пул свободных псевдонимов.

    Выдача заранее созданного псевдонима разрывает корреляцию «begins псевдонима ≈
    begins моста». Строка удаляется при выдаче; временных меток у пула нет —
    дамп БД показывает только КАКИЕ псевдонимы свободны, но не когда занят занятый.
    """
    __tablename__ = "pseudonym_pool"

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, ForeignKey("pseudonym.id"),
                                          primary_key=True)


class Link(CrossTable):
    """Мост псевдонимизации: payload = Enc(DEK, pseudonym_id).

    Открытая сторона — субъект (table, objectid: персона ИЛИ компания — любой
    identity-объект, охраняется в _register_new_objects) и контур данных (scope).
    На псевдоним открытой ссылки НЕТ и не должно быть — целостность этой связи
    обеспечивается криптографией и приложением, это единственное осознанное
    исключение из реестра объектов.
    """

    scope: Mapped[str] = mapped_column(String)      # контур: medical | financial | contact
    payload: Mapped[bytes] = mapped_column(BYTEA)   # Enc(DEK, pseudonym_id)

    __local_table_args__ = (
        Index('uq_link_subject_scope', 'table', 'objectid', 'scope',
              unique=True, postgresql_where=ACTIVE),
    )


class Access(Base):
    """Копия DEK контура, зашифрованная для получателя.

    Получатели: owner (пациент; в проде шифруется на клиенте его ключом,
    key_id тогда NULL), group (групповой ключ в KeyService, recipient — id
    группы в реестре), escrow (break-glass, recipient NULL). Отзыв доступа =
    expire строки.
    """
    __domain__ = Domain.IDENTITY

    link: Mapped[uuid6.UUID] = mapped_column(UUID_TYPE, ForeignKey("link.id"), index=True)
    recipient_type: Mapped[str] = mapped_column(String)  # owner | group | escrow
    recipient: Mapped[uuid6.UUID | None] = mapped_column(UUID_TYPE, ForeignKey("object.id"),
                                                         nullable=True)
    key_id: Mapped[str | None] = mapped_column(String, nullable=True)  # ключ в KeyService
    wrapped_dek: Mapped[bytes] = mapped_column(BYTEA)

    __local_table_args__ = (
        Index('uq_access_link_recipient', 'link', 'recipient_type', 'recipient',
              unique=True, postgresql_where=ACTIVE),
    )
