from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from fastapi import HTTPException

from sqlalchemy.exc import IntegrityError

from ..cache import get_cache
from ..keyservice import get_key_service
from ..models.auth import Challenge, KeyCredentials, Token
from ..models.user import Contact, SignUp, SignUpConfirm, User, password_issues
from ..services.mailer import pop_signup, request_signup
from ..services.medaccess import enroll_patient
from ..services.user import UserService
from ..services.auth import AuthService, get_current_user
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


@router.post('/signup/', status_code=status.HTTP_204_NO_CONTENT,
             dependencies=[Depends(rate_limit)])
async def sign_up(data: SignUp, service: UserService = Depends()):
    """Шаг 1 регистрации: заявка в Redis + код на почту. Учётка НЕ создаётся —
    неподтверждённая заявка испаряется по TTL (анти-спам левыми адресами)."""
    email = _prop(data.contact.email, None)
    if issues := password_issues(data.password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='weak_password: ' + ','.join(issues))
    if await service.get_by_contact(email) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail='contact_taken')
    # троттлинг по адресу: коды на чужой ящик нельзя слать бесконечно
    if not await get_cache().hit(f'signupmail:{email.lower()}',
                                 settings.signup_mail_limit, 3600):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail='too_many_attempts')
    pending = data.model_dump(mode='json', exclude={'password'})
    pending['password_hash'] = AuthService.hash_password(data.password)
    await request_signup(service.session, email, pending)
    await service.session.commit()          # письмо — через outbox


@router.post('/signup/confirm/', response_model=Token,
             status_code=status.HTTP_201_CREATED, dependencies=[Depends(rate_limit)])
async def sign_up_confirm(body: SignUpConfirm, service: UserService = Depends()):
    """Шаг 2: код сошёлся — создаются персона, учётка (confirmed) и ключи карты."""
    pending = await pop_signup(body.email, body.code)
    if pending is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='confirm_code_invalid')
    password_hash = pending.pop('password_hash')
    # пароль-заглушка проходит валидацию и не используется: хеш уже готов
    signup = SignUp.model_validate({**pending, 'password': '<confirmed>'})
    try:
        token, user = await service.register_new_user(signup, password_hash)
    except IntegrityError:                  # гонка двух подтверждений
        await service.session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail='contact_taken') from None
    # ключи выпускаются каждому при регистрации (решение владельца)
    await enroll_patient(service.session, get_key_service(), user.id, user.person)
    return token


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
