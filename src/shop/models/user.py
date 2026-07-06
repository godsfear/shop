import uuid

from pydantic import BaseModel, Field

from .base import ReadMixin


class Contact(BaseModel):
    """Контакты пользователя; хранятся в JSONB-поле user.contact."""
    email: str | None = None
    phone: str | None = None


class UserBase(BaseModel):
    person: uuid.UUID
    contact: Contact


class UserCreate(UserBase):
    password: str = Field(min_length=8)
    public_key: str = ''


class UserUpdate(BaseModel):
    contact: Contact | None = None
    password: str | None = Field(default=None, min_length=8)
    public_key: str | None = None


class UserRoles(BaseModel):
    """Выдача ролей — отдельная операция, только для администратора."""
    roles: list[str]


class User(UserBase, ReadMixin):
    validated: bool = False
    roles: list[str] = []
