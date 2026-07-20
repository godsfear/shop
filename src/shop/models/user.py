import uuid

from pydantic import BaseModel, Field

from .base import ReadMixin
from .person import PersonCreate


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


def password_issues(password: str) -> list[str]:
    """Каких требований сложности не хватает — коды для 'weak_password: ...'.
    Проверка на входе (signup/смена пароля): в заявке и БД живёт только хеш."""
    issues = []
    if len(password) < 8:
        issues.append('length')
    if not any(c.islower() for c in password):
        issues.append('lower')
    if not any(c.isupper() for c in password):
        issues.append('upper')
    if not any(c.isdigit() for c in password):
        issues.append('digit')
    return issues


class SignUp(BaseModel):
    """Регистрация: персона создаётся вместе с учёткой одной транзакцией."""
    person: PersonCreate
    contact: Contact
    password: str = Field(min_length=8)
    public_key: str = ''
    # согласие на обработку ПДн: клиент лишь подтверждает факт (True), версию
    # и момент фиксирует сервер (нельзя доверять клиенту в юридическом следе)
    terms_accepted: bool = False


class UserUpdate(BaseModel):
    contact: Contact | None = None
    password: str | None = Field(default=None, min_length=8)
    public_key: str | None = None


class UserRoles(BaseModel):
    """Выдача ролей — отдельная операция, только для администратора."""
    roles: list[str]


class SignUpConfirm(BaseModel):
    """Шаг 2 регистрации: почта + код из письма (заявка — в Redis)."""
    email: str
    code: str


class User(UserBase, ReadMixin):
    roles: list[str] = []
    confirmed: bool = False   # почта подтверждена кодом
