import uuid

from fastapi import APIRouter, Body, Depends

from ..models.auth import TokenPayload
from ..models.fsm import FSMState
from ..services.auth import get_token_payload
from ..services.fsm import FSMService

router = APIRouter(prefix='/fsm', tags=['fsm'])


@router.get('/{table}/{objectid}', response_model=FSMState)
async def get_state(table: str, objectid: uuid.UUID, service: FSMService = Depends(),
                    payload: TokenPayload = Depends(get_token_payload)):
    return await service.state(table, objectid)


@router.post('/{table}/{objectid}/{event}', response_model=FSMState)
async def trigger_event(table: str, objectid: uuid.UUID, event: str,
                        context: dict = Body(default={}),
                        service: FSMService = Depends(),
                        payload: TokenPayload = Depends(get_token_payload)):
    """Выполнить переход; context передаётся guard'ам и action'ам."""
    return await service.trigger(table, objectid, event, creator=payload.sub, context=context)
