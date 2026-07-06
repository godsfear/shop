import uuid

from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class TokenPayload(BaseModel):
    """Содержимое JWT: только субъект и роли, никаких персональных данных."""
    sub: uuid.UUID
    roles: list[str] = []


class Challenge(BaseModel):
    """Nonce для входа по ключу: клиент подписывает raw-байты (base64-декод)."""
    nonce: str  # base64


class KeyCredentials(BaseModel):
    """Вход по ключу: контакт для поиска учётки + подпись nonce приватным ключом."""
    email: str | None = None
    phone: str | None = None
    signature: str  # base64 подписи raw-байтов nonce (Ed25519)
