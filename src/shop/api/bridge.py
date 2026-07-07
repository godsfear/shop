"""API моста псевдонимизации.

ЖЕЛЕЗНОЕ ПРАВИЛО (память проекта, «шов №2»): actor для ACL ключевого сервиса
и сессионного кэша — ТОЛЬКО payload.sub из токена, никогда из тела запроса.
Гранты групповых ключей в KeyService выдаются на str(user_id).
"""
import base64
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from ..models.auth import TokenPayload
from typing import List

from ..models.bridge import (AccessInfo, AccessOut, BreakglassRequest, GrantRequest,
                             LinkCreate, LinkOut, PseudonymOut, ResolveRequest)
from ..services.auth import get_token_payload
from ..services.bridge import BridgeService

router = APIRouter(prefix='/bridge', tags=['bridge'])


def _b64(value: str, what: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f'{what}: некорректный base64') from None


@router.post('/link', response_model=LinkOut, status_code=status.HTTP_201_CREATED)
async def create_link(data: LinkCreate, service: BridgeService = Depends(),
                      payload: TokenPayload = Depends(get_token_payload)):
    owner_wrapped = _b64(data.owner_wrapped_b64, 'owner_wrapped_b64') \
        if data.owner_wrapped_b64 else None
    link, pseudonym = await service.create_link(
        data.subject_table, data.subject_id, data.scope,
        groups=data.groups, owner_wrapped=owner_wrapped)
    return LinkOut(link=link.id, pseudonym=pseudonym)


@router.post('/link/{link_id}/resolve', response_model=PseudonymOut)
async def resolve_link(link_id: uuid.UUID, data: ResolveRequest,
                       service: BridgeService = Depends(),
                       payload: TokenPayload = Depends(get_token_payload)):
    pseudonym = await service.resolve(link_id, data.key_id, actor=str(payload.sub))
    return PseudonymOut(pseudonym=pseudonym)


@router.post('/link/{link_id}/breakglass', response_model=PseudonymOut)
async def breakglass_resolve(link_id: uuid.UUID, data: BreakglassRequest,
                             service: BridgeService = Depends(),
                             payload: TokenPayload = Depends(get_token_payload)):
    pseudonym = await service.breakglass_resolve(link_id, data.request_id)
    return PseudonymOut(pseudonym=pseudonym)


@router.post('/link/{link_id}/grant', response_model=AccessOut,
             status_code=status.HTTP_201_CREATED)
async def grant_access(link_id: uuid.UUID, data: GrantRequest,
                       service: BridgeService = Depends(),
                       payload: TokenPayload = Depends(get_token_payload)):
    """Выдать доступ: только владелец субъекта моста или администратор."""
    access = await service.add_recipient(link_id, data.key_id, data.recipient,
                                         _b64(data.dek_b64, 'dek_b64'),
                                         recipient_type=data.recipient_type,
                                         payload=payload)
    return AccessOut(access=access.id)


@router.get('/link/{link_id}/access', response_model=List[AccessInfo])
async def list_access(link_id: uuid.UUID, service: BridgeService = Depends(),
                      payload: TokenPayload = Depends(get_token_payload)):
    """Кому выдан доступ по мосту (владелец/админ; без шифртекстов)."""
    return await service.list_access(link_id, payload)


@router.delete('/link/{link_id}/access/{access_id}', response_model=AccessInfo)
async def revoke_access(link_id: uuid.UUID, access_id: uuid.UUID,
                        service: BridgeService = Depends(),
                        payload: TokenPayload = Depends(get_token_payload)):
    """Отозвать доступ (escrow-копию отозвать нельзя)."""
    return await service.revoke_access(link_id, access_id, payload)
