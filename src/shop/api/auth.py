from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from fastapi import HTTPException

from ..cache import get_cache
from ..models.auth import Challenge, KeyCredentials, Token
from ..models.user import Contact, SignUp, User
from ..services.user import UserService
from ..services.auth import get_current_user
from ..settings import settings

router = APIRouter(prefix='/auth', tags=['auth'])


async def rate_limit(request: Request) -> None:
    """Троттлинг по IP: brute-force пароля и enumeration через signup/challenge.
    Redis недоступен — пропускаем (мягкая деградация, как весь кэш)."""
    ip = request.client.host if request.client else 'unknown'
    if not await get_cache().hit(f'auth:{ip}', settings.auth_rate_limit,
                                 settings.auth_rate_window_s):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail='слишком много попыток — повторите позже')


def _prop(email: str | None, phone: str | None) -> str:
    prop = email or phone
    if not prop:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='Нужен email или phone')
    return prop


@router.post('/signup/', response_model=Token, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit)])
async def sign_up(data: SignUp, service: UserService = Depends()):
    """Регистрация: персона создаётся внутри signup, отдельный шаг не нужен."""
    return await service.register_new_user(data)


@router.post('/signin/', response_model=Token, dependencies=[Depends(rate_limit)])
async def sign_in(auth_data: OAuth2PasswordRequestForm = Depends(), service: UserService = Depends()):
    return await service.authenticate_user(auth_data.username, auth_data.password)


@router.post('/challenge/', response_model=Challenge, dependencies=[Depends(rate_limit)])
async def create_challenge(contact: Contact, service: UserService = Depends()):
    """Шаг 1 входа по ключу: одноразовый nonce (подписать raw-байты base64-декода)."""
    return await service.create_challenge(_prop(contact.email, contact.phone))


@router.post('/signin/key/', response_model=Token, dependencies=[Depends(rate_limit)])
async def sign_in_by_key(credentials: KeyCredentials, service: UserService = Depends()):
    """Шаг 2 входа по ключу: подпись nonce -> JWT."""
    return await service.authenticate_by_key(
        _prop(credentials.email, credentials.phone), credentials.signature)


@router.get('/user/', response_model=User)
async def get_user(user=Depends(get_current_user)):
    return user
