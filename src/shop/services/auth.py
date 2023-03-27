from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.hash import bcrypt
from pydantic import ValidationError

from .. import tables
from ..models.user import User
from ..models.auth import Token
from ..settings import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/auth/signin/')


class AuthService:
    @classmethod
    def get_current_user(cls, token: str = Depends(oauth2_scheme)) -> User:
        return cls.verify_token(token)

    @classmethod
    def verify_password(cls, plain_password: str, hashed_password: str) -> bool:
        return bcrypt.verify(plain_password, hashed_password)

    @classmethod
    def hash_password(cls, password: str) -> str:
        return bcrypt.hash(password)

    @classmethod
    def verify_token(cls, token: str) -> User:
        exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Could not validate credentials',
            headers={'WWW-Authenticate': 'Bearer'},
        )
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
            )
        except JWTError:
            raise exception from None
        user_data = payload.get('user')
        try:
            user = User.parse_obj(user_data)
        except ValidationError:
            raise exception from None
        return user

    @classmethod
    def create_token(cls, user: tables.User) -> Token:
        user_data = User.from_orm(user)
        now = datetime.utcnow()
        payload = {
            'iat': now,
            'nbf': now,
            'exp': now + timedelta(seconds=settings.jwt_expires_s),
            'sub': str(user_data.id),
            'user': user_data.dict(),
        }
        token = jwt.encode(
            payload,
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )
        return Token(access_token=token)
