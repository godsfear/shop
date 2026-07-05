"""Общие строительные блоки моделей API.

Соглашение по именам в каждом модуле:
- XxxBase   — общие клиентские поля (используются в создании и чтении);
- XxxCreate — тело POST: без id/begins/ends/creator, их заполняет сервер;
- XxxUpdate — тело PATCH: все поля необязательные, сервис применяет
              только переданные (model_dump(exclude_unset=True));
- XxxFilter — критерии поиска, все поля необязательные;
- Xxx       — модель ответа (читается из ORM-объекта).
"""
import datetime
import uuid

from pydantic import BaseModel, ConfigDict


class ReadMixin(BaseModel):
    """Системные поля записи — генерируются сервером."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    begins: datetime.datetime
    ends: datetime.datetime | None = None


class CreatorMixin(BaseModel):
    """Автор записи; заполняется сервером из токена, а не из тела запроса."""
    creator: uuid.UUID | None = None
