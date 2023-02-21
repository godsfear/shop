from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from ..models.auth import Token
from ..models.user import UserCreate, User
from ..services.auth import AuthService

router = APIRouter(prefix='/auth', tags=['auth'])


@router.post('/signup/', response_model=Token, status_code=status.HTTP_201_CREATED)
async def sign_up(user_data: UserCreate, auth_service: AuthService = Depends()):
    return await auth_service.register_new_user(user_data)


@router.post('/signin/', response_model=Token)
async def sign_in(auth_data: OAuth2PasswordRequestForm = Depends(), auth_service: AuthService = Depends()):
    return await auth_service.authenticate_user(auth_data.username,auth_data.password)


@router.get('/user/', response_model=User)
async def get_user(user: User = Depends(AuthService.get_current_user)):
    return user
