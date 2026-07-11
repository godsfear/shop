import uuid

from pydantic import BaseModel, field_validator

from .base import CreatorMixin, ReadMixin


def forbid_state_code(v: str) -> str:
    """'state' зарезервирован FSM (services/fsm.STATE_CODE): состояние объекта
    меняется только переходом, иначе клиент подделал бы его в обход машины."""
    if v == 'state':
        raise ValueError("код 'state' зарезервирован машиной состояний — используйте /transition")
    return v


class PropertyBase(BaseModel):
    category: uuid.UUID | None = None
    code: str
    name: str | None = None
    description: str | None = None
    table: str                       # тип объекта-носителя (pseudonym, entity, ...)
    objectid: uuid.UUID
    value: dict


class PropertyCreate(PropertyBase):
    _code_not_reserved = field_validator('code')(forbid_state_code)


class PropertyUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    description: str | None = None
    value: dict | None = None

    _code_not_reserved = field_validator('code')(forbid_state_code)


class PropertyFilter(BaseModel):
    table: str | None = None
    objectid: uuid.UUID | None = None
    category: uuid.UUID | None = None
    code: str | None = None


class Property(PropertyBase, ReadMixin, CreatorMixin):
    pass
