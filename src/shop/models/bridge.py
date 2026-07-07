import uuid
from typing import Literal

from pydantic import BaseModel

from .base import ReadMixin


class LinkCreate(BaseModel):
    subject_table: str                          # 'person' | 'company' (identity-объект)
    subject_id: uuid.UUID
    scope: str                                  # контур: medical | financial | contact
    groups: dict[str, uuid.UUID | None] = {}    # key_id в KeyService -> id группы в реестре
    owner_wrapped_b64: str | None = None        # Enc(ключ владельца, DEK), изготовлен клиентом


class LinkOut(BaseModel):
    """Создателю моста связь известна по определению — псевдоним возвращается
    ему для создания операционных данных и не должен уходить дальше."""
    link: uuid.UUID
    pseudonym: uuid.UUID


class ResolveRequest(BaseModel):
    key_id: str          # ключ группы в KeyService; actor берётся из токена


class BreakglassRequest(BaseModel):
    request_id: str      # одобренная break-glass заявка в KeyService


class GrantRequest(BaseModel):
    """Грант нового получателя; DEK расшифровывает владелец на клиенте."""
    key_id: str
    recipient: uuid.UUID | None = None
    recipient_type: Literal['group', 'user'] = 'group'
    dek_b64: str


class PseudonymOut(BaseModel):
    pseudonym: uuid.UUID


class AccessOut(BaseModel):
    access: uuid.UUID


class AccessInfo(ReadMixin):
    """Строка круга доступа — без шифртекстов."""
    recipient_type: str
    recipient: uuid.UUID | None
    key_id: str | None
