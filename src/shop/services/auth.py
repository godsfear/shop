import bcrypt
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import ValidationError

from shop.database import serialize2str
from shop import tables
from shop.models.user import User
from shop.models.auth import Token
from shop.settings import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/auth/signin/')


class AuthService:
    @classmethod
    def get_current_user(cls, token: str = Depends(oauth2_scheme)) -> User:
        return cls.verify_token(token)

    @classmethod
    def verify_password(cls, plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())

    @classmethod
    def hash_password(cls, password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

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
            user = User.model_validate(user_data)
        except ValidationError:
            raise exception from None
        return user

    @classmethod
    def create_token(cls, user: tables.User) -> Token:
        user_data = User.model_validate(user)
        now = datetime.utcnow()
        payload = {
            'iat': now,
            'nbf': now,
            'exp': now + timedelta(seconds=settings.jwt_expires_s),
            'sub': str(user_data.id),
            'user': serialize2str(user_data.model_dump()),
        }
        token = jwt.encode(
            payload,
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )
        return Token(access_token=token)
