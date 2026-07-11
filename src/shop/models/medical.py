"""Модели медицинского API. Ключевое: OUT-проекция НЕ несёт objectid/table —
псевдоним (носитель медданных) не попадает в поверхность API."""
import datetime
import uuid

from pydantic import BaseModel, ConfigDict


class SessionOpen(BaseModel):
    """Открытие сессии доступа: разворот моста по (link_id, key_id) -> псевдоним в Redis."""
    link_id: uuid.UUID
    key_id: str


class MedPropertyIn(BaseModel):
    """Медицинский факт от клиента; носитель (псевдоним) подставляет сервер из сессии."""
    category: uuid.UUID | None = None
    code: str
    name: str | None = None
    value: dict


class MedPropertyOut(BaseModel):
    """Проекция Property БЕЗ objectid/table — псевдоним скрыт из поверхности API."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: uuid.UUID | None = None
    code: str
    name: str | None = None
    value: dict
    begins: datetime.datetime
    ends: datetime.datetime | None = None


class EpisodeIn(BaseModel):
    """Открытие эпизода (болезнь/травма); носитель (псевдоним) ставит сервер."""
    category: uuid.UUID              # концепт illness|injury (Category.id)
    code: str
    name: str | None = None


class EpisodeOut(BaseModel):
    """Проекция эпизода БЕЗ objectid/table — эпизод висит на псевдониме, его прячем."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: uuid.UUID | None = None
    code: str
    name: str | None = None
    begins: datetime.datetime
    ends: datetime.datetime | None = None


class Transition(BaseModel):
    """FSM-переход эпизода: событие (diagnose|treat|recover|remit|relapse)."""
    event: str


class DataOut(BaseModel):
    """Проекция Data (метаданные документа/анализа) БЕЗ objectid/table.
    hash — контент-адрес блоба в FileStore (не псевдоним, отдавать можно)."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: uuid.UUID | None = None
    code: str
    name: str | None = None
    hash: str
    algorithm: str
    begins: datetime.datetime
    ends: datetime.datetime | None = None
