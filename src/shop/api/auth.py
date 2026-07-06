from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from fastapi import HTTPException

from ..models.auth import Challenge, KeyCredentials, Token
from ..models.user import Contact, SignUp, User
from ..services.user import UserService
from ..services.auth import get_current_user

router = APIRouter(prefix='/auth', tags=['auth'])


def _prop(email: str | None, phone: str | None) -> str:
    prop = email or phone
    if not prop:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='Нужен email или phone')
    return prop


@router.post('/signup/', response_model=Token, status_code=status.HTTP_201_CREATED)
async def sign_up(data: SignUp, service: UserService = Depends()):
    """Регистрация: персона создаётся внутри signup, отдельный шаг не нужен."""
    return await service.register_new_user(data)


@router.post('/signin/', response_model=Token)
async def sign_in(auth_data: OAuth2PasswordRequestForm = Depends(), service: UserService = Depends()):
    return await service.authenticate_user(auth_data.username, auth_data.password)


@router.post('/challenge/', response_model=Challenge)
async def create_challenge(contact: Contact, service: UserService = Depends()):
    """Шаг 1 входа по ключу: одноразовый nonce (подписать raw-байты base64-декода)."""
    return await service.create_challenge(_prop(contact.email, contact.phone))


@router.post('/signin/key/', response_model=Token)
async def sign_in_by_key(credentials: KeyCredentials, service: UserService = Depends()):
    """Шаг 2 входа по ключу: подпись nonce -> JWT."""
    return await service.authenticate_by_key(
        _prop(credentials.email, credentials.phone), credentials.signature)


@router.get('/user/', response_model=User)
async def get_user(user=Depends(get_current_user)):
    return user
