import datetime
import uuid

from pydantic import BaseModel

from .base import ReadMixin


class ConsentRequest(BaseModel):
    subject_table: str            # person | company
    subject_id: uuid.UUID
    scope: str                    # identity | contact | medical | financial | manage
    reason: str | None = None


class ManageGrant(BaseModel):
    """Назначение управляющего: полный manage-доступ к субъекту."""
    subject_table: str
    subject_id: uuid.UUID
    grantee: uuid.UUID


class ConsentDecision(BaseModel):
    """Параметры одобрения; deny/revoke параметров не имеют."""
    until: datetime.datetime | None = None   # срок действия, NULL = бессрочно


class Consent(ReadMixin):
    table: str
    objectid: uuid.UUID
    grantee: uuid.UUID
    scope: str
    status: str
    until: datetime.datetime | None
    reason: str | None
