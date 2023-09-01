import uuid
from fastapi import APIRouter, Depends
from typing import List

from ..models.account import Account, AccountCreate, AccountUpdate, AccountBase
from ..services.account import AccountService

router = APIRouter(prefix='/account', tags=['account'])


@router.get('/all', response_model=List[Account])
async def get_account(service: AccountService = Depends()):
    account = await service.get_all()
    return account


@router.get('/{account_id}', response_model=Account)
async def get_account_by_id(account_id: uuid.UUID, service: AccountService = Depends()):
    account = await service.get_by_id(account_id)
    return account


@router.post('/', response_model=Account)
async def create_account(account_data: AccountCreate, service: AccountService = Depends()):
    account = await service.create(account_data)
    return account


@router.post('/category_code', response_model=List[Account])
async def get_account_by_category_code(account_data: AccountBase, service: AccountService = Depends()):
    account = await service.get_by_category_code(account_data)
    return account


@router.put('/{account_id}', response_model=Account)
async def update_account(account_id: uuid.UUID, account_data: AccountUpdate, service: AccountService = Depends()):
    account = await service.update(account_id, account_data)
    return account


@router.delete('/{account_id}', response_model=Account)
async def delete_account(account_id: uuid.UUID, service: AccountService = Depends()):
    account = await service.expire(account_id)
    return account
