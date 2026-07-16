from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from fastapi import HTTPException

from ..cache import get_cache
from ..keyservice import get_key_service
from ..models.auth import Challenge, KeyCredentials, Token, TokenPayload
from ..models.user import ConfirmCode, Contact, SignUp, User
from ..services.mailer import check_confirm, request_confirm
from ..services.medaccess import enroll_patient
from ..services.user import UserService
from ..services.auth import get_current_user, get_token_payload
from ..settings import settings

router = APIRouter(prefix='/auth', tags=['auth'])


async def rate_limit(request: Request) -> None:
    """Троттлинг по IP: brute-force пароля и enumeration через signup/challenge.
    Redis недоступен — пропускаем (мягкая деградация, как весь кэш)."""
    ip = request.client.host if request.client else 'unknown'
    if not await get_cache().hit(f'auth:{ip}', settings.auth_rate_limit,
                                 settings.auth_rate_window_s):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail='too_many_attempts')


def _prop(email: str | None, phone: str | None) -> str:
    prop = email or phone
    if not prop:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='contact_required')
    return prop


@router.post('/signup/', response_model=Token, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit)])
async def sign_up(data: SignUp, service: UserService = Depends()):
    """Регистрация: персона, учётка и ключи карты — сразу; на почту уходит код."""
    token, user = await service.register_new_user(data)
    # ключи выпускаются каждому при регистрации (решение владельца) —
    # отдельного шага «завести карту» нет
    await enroll_patient(service.session, get_key_service(), user.id, user.person)
    return token


@router.post('/confirm/', response_model=User, dependencies=[Depends(rate_limit)])
async def confirm_email(body: ConfirmCode, service: UserService = Depends(),
                        payload: TokenPayload = Depends(get_token_payload)):
    """Подтверждение почты кодом из письма (без него нельзя запрашивать чужие карты)."""
    if not await check_confirm(payload.sub, body.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='confirm_code_invalid')
    return await service.confirm(payload.sub)


@router.post('/confirm/resend/', status_code=status.HTTP_204_NO_CONTENT,
             dependencies=[Depends(rate_limit)])
async def resend_confirm(service: UserService = Depends(),
                         payload: TokenPayload = Depends(get_token_payload)):
    user = await service.get_by_id(payload.sub)
    email = user.contact.email
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='no_email_in_profile')
    await request_confirm(service.session, payload.sub, email)
    await service.session.commit()


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
