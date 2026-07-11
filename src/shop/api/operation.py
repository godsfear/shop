import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, status

from ..models.auth import TokenPayload
from ..models.operation import Balance, Operation, OperationCreate
from ..services.auth import get_token_payload, require_admin
from ..services.operation import OperationService

# финансовые операции: owner-скоупа ещё нет — до его появления только админ
router = APIRouter(prefix='/operation', tags=['operation'],
                   dependencies=[Depends(require_admin)])


@router.post('/', response_model=Operation, status_code=status.HTTP_201_CREATED)
async def create_operation(data: OperationCreate, service: OperationService = Depends(),
                           payload: TokenPayload = Depends(get_token_payload)):
    """Проводка записывается сразу; балансы пересчитываются асинхронно (outbox)."""
    return await service.create(data, creator=payload.sub)


@router.get('/balance/{account_id}', response_model=Balance)
async def get_balance(account_id: uuid.UUID, service: OperationService = Depends(),
                      payload: TokenPayload = Depends(get_token_payload)):
    value: Decimal = await service.balance(account_id)
    return Balance(account=account_id, value=value)
