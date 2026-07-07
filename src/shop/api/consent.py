import uuid
from typing import List

from fastapi import APIRouter, Body, Depends, status

from ..models.auth import TokenPayload
from ..models.consent import Consent, ConsentDecision, ConsentRequest, ManageGrant
from ..services.auth import get_token_payload
from ..services.consent import ConsentService

router = APIRouter(prefix='/consent', tags=['consent'])


@router.post('/request', response_model=Consent, status_code=status.HTTP_201_CREATED)
async def request_consent(data: ConsentRequest, service: ConsentService = Depends(),
                          payload: TokenPayload = Depends(get_token_payload)):
    """Запросить доступ к данным субъекта; решает владелец/управляющий."""
    return await service.request(data, payload)


@router.post('/manage', response_model=Consent, status_code=status.HTTP_201_CREATED)
async def grant_manage(data: ManageGrant, service: ConsentService = Depends(),
                       payload: TokenPayload = Depends(get_token_payload)):
    """Назначить управляющего (владелец/управляющий/админ)."""
    return await service.grant_manage(data.subject_table, data.subject_id,
                                      data.grantee, payload)


@router.get('/incoming', response_model=List[Consent])
async def incoming_requests(service: ConsentService = Depends(),
                            payload: TokenPayload = Depends(get_token_payload)):
    """Ожидающие моего решения запросы (я — владелец или управляющий)."""
    return await service.incoming(payload)


@router.get('/mine', response_model=List[Consent])
async def my_consents(service: ConsentService = Depends(),
                      payload: TokenPayload = Depends(get_token_payload)):
    """Мои запросы и действующие согласия."""
    return await service.mine(payload)


@router.post('/{consent_id}/approve', response_model=Consent)
async def approve_consent(consent_id: uuid.UUID,
                          decision: ConsentDecision = Body(default=ConsentDecision()),
                          service: ConsentService = Depends(),
                          payload: TokenPayload = Depends(get_token_payload)):
    return await service.decide(consent_id, True, decision, payload)


@router.post('/{consent_id}/deny', response_model=Consent)
async def deny_consent(consent_id: uuid.UUID, service: ConsentService = Depends(),
                       payload: TokenPayload = Depends(get_token_payload)):
    return await service.decide(consent_id, False, ConsentDecision(), payload)


@router.post('/{consent_id}/revoke', response_model=Consent)
async def revoke_consent(consent_id: uuid.UUID, service: ConsentService = Depends(),
                         payload: TokenPayload = Depends(get_token_payload)):
    return await service.revoke(consent_id, payload)
