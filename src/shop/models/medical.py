"""Модели медицинского API. Ключевое: OUT-проекция НЕ несёт objectid/table —
псевдоним (носитель медданных) не попадает в поверхность API."""
import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .property import forbid_state_code


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

    _code_not_reserved = field_validator('code')(forbid_state_code)


class SleepIn(BaseModel):
    """Запись ночи в дневник сна: дата (утренняя) + показатели ночи."""
    day: str
    value: dict


class _MedOut(BaseModel):
    """Общая проекция мед-ответов: БЕЗ objectid/table — псевдоним (носитель
    медданных) не попадает в поверхность API. Инвариант держится здесь одним
    местом, а не дисциплиной каждой конкретной модели."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: uuid.UUID | None = None
    code: str
    name: str | None = None
    begins: datetime.datetime
    ends: datetime.datetime | None = None


class MedPropertyOut(_MedOut):
    value: dict


class AnamnesisEdit(BaseModel):
    """Правка ответа на слот анамнеза (опечатки) — только до постановки
    диагноза. associations не редактируется (структурный слот — очередь
    разбора уже отработала)."""
    symptom: str = Field(min_length=1, max_length=100)
    slot: str = Field(min_length=1, max_length=50)
    value: str | int | float


class DiagnosisIn(BaseModel):
    """Установленный диагноз: вручную или выбор из ИИ-вариантов (ddx)."""
    text: str = Field(min_length=2, max_length=500)
    source: str = 'manual'          # manual | ddx


class TreatmentItem(BaseModel):
    code: str | None = None         # стабильный id из плана ИИ (если выбран оттуда)
    name: str = Field(min_length=1, max_length=500)


class TreatmentIn(BaseModel):
    """Назначения при старте лечения: выбранные из плана ИИ и/или свои."""
    items: list[TreatmentItem] = Field(min_length=1)


class EpisodeIn(BaseModel):
    """Открытие эпизода (болезнь/травма); носитель (псевдоним) ставит сервер."""
    category: uuid.UUID              # концепт illness|injury (Category.id)
    code: str
    name: str | None = None


class EpisodeOut(_MedOut):
    pass


class EpisodeRename(BaseModel):
    """Название эпизода появляется ПОСЛЕ диагноза — при создании его ещё нет."""
    name: str


class Transition(BaseModel):
    """FSM-переход эпизода: событие (diagnose|treat|recover|remit|relapse)."""
    event: str


class DataOut(_MedOut):
    """hash — контент-адрес блоба в FileStore (не псевдоним, отдавать можно)."""
    hash: str
    algorithm: str
