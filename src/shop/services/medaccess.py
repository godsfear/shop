"""Доступ к медданным через сессионный гибрид (память проекта: API Property).

Медданные висят на псевдониме (operational). Псевдоним в поверхность API НЕ
попадает: он разворачивается из моста ОДИН раз при открытии сессии и живёт в
Redis (medsession:{sub}, TTL) — запросы авторизуются сессией, читают/пишут по
скоупу этого псевдонима. Отзыв — по истечении TTL или на следующем открытии.

Разворот — существующий bridge.resolve (ACL ключа + аудит + кэш). Слой owner
(сам пациент): ceiling — в проде owner-DEK на клиенте, здесь MVP резолвит по
серверному ключу пациента (стенд-ин клиентской крипты). Слой b (врач/близкий):
тот же resolve по гранту группы — см. resolve_link (Слой B).
"""
import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..cache import get_cache
from ..database import db_helper
from ..keyservice import KeyServiceError, PolicyError
from ..medical_seed import medical_concepts
from ..models.auth import TokenPayload
from ..models.entity import EntityCreate
from ..models.medical import EpisodeIn, MedPropertyIn
from ..models.property import PropertyCreate, PropertyFilter
from ..services.auth import get_token_payload
from ..services.bridge import BridgeService
from ..services.consent import APPROVED, MEDICAL, _until_alive
from ..services.entity import EntityService
from ..services.extract import request_extract
from ..services.files import FileStore
from ..services.fsm import FSMService
from ..services.interview import InterviewService
from ..services.medical import MedicalService
from ..services.property import PropertyService
from ..settings import settings
from .. import tables

_SESSION_NS = 'medsession'


class MedAccessService:
    """Сессия + доступ к медданным пациента (по псевдониму), НЕ сущность-CRUD.

    Работает со скоупом псевдонима (Pseudonym, «пациент №...»), а не с Person:
    личность и медданные развязаны псевдонимизацией, ключом Person здесь быть
    не должно."""

    def __init__(self, session=Depends(db_helper.scoped_session_dependency),
                 bridge: BridgeService = Depends(),
                 payload: TokenPayload = Depends(get_token_payload)):
        self.session = session
        self.bridge = bridge
        self.payload = payload

    # --- онбординг: выпуск моста пациента (MVP-стенд-ин, KeyService — заглушка) ---
    async def enroll(self) -> None:
        """Идемпотентно выпускает медицинский мост пациента: ключ patient:{sub} +
        грант + Link(person,'medical'). Это «выпуск ключей» MVP — серверный стенд-ин
        клиентской крипты (ceiling: owner-DEK в проде на клиенте, KeyService не заглушка)."""
        person_id = await self._person_id()
        if await self._owner_link(person_id) is not None:
            return                                  # уже выпущен
        keys = self.bridge.keys
        for kid in ('escrow', self._patient_key()):  # escrow — общесистемный (break-glass)
            try:
                await keys.create_key(kid)
            except KeyServiceError:
                pass                                # ключ уже существует
        await keys.grant(self._patient_key(), str(self.payload.sub))
        try:
            await self.bridge.create_link('person', person_id, 'medical',
                                          groups={self._patient_key(): person_id})
        except IntegrityError:
            # конкурентный enroll уже выпустил мост (uq_link_subject_scope) — идемпотентно
            await self.session.rollback()
        # re-sync: медицинские согласия, одобренные ДО enroll (ключа ещё не было),
        # догрантиваются здесь — connect-точка Consent -> KeyService (см. consent.py)
        grantees = (await self.session.execute(select(tables.Consent.grantee).where(
            tables.Consent.table == 'person', tables.Consent.objectid == person_id,
            tables.Consent.scope == MEDICAL, tables.Consent.status == APPROVED,
            _until_alive()))).scalars().all()
        for grantee in grantees:
            await keys.grant(self._patient_key(), str(grantee))

    # --- сессия (ТОЛЬКО Слой A: owner). Слой B (врач/близкий) сессию не использует:
    # он stateless — link_id/key_id в каждом запросе (см. _resolve); делегированная
    # сессия перезаписала бы owner-псевдоним под тем же ключом medsession:{sub},
    # и запросы «моей» карты писали бы в чужую.
    async def open_session(self) -> int:
        """Авто-дискавери своего моста по JWT -> псевдоним в Redis-сессию; TTL (сек)."""
        person_id = await self._person_id()
        link = await self._owner_link(person_id)
        if link is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail='медицинский мост не выпущен — сначала /me/enroll')
        try:
            pseudonym = await self.bridge.resolve(link.id, self._patient_key(),
                                                  str(self.payload.sub))
        except (PolicyError, KeyServiceError):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail='нет доступа к своему мосту (ключ пациента)')
        # Redis здесь — хранилище сессии, а не кэш: молчаливый no-op означал бы
        # 200 «сессия открыта» и сплошные 401 на каждом следующем запросе
        if not await get_cache().set(self._key(), str(pseudonym), settings.medsession_ttl_s):
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail='хранилище сессий недоступно — повторите позже')
        return settings.medsession_ttl_s

    def _patient_key(self) -> str:
        return f'patient:{self.payload.sub}'

    async def _person_id(self) -> uuid.UUID:
        person = (await self.session.execute(select(tables.User.person).where(
            tables.User.id == self.payload.sub))).scalar_one_or_none()
        if person is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail='пользователь не найден')
        return person

    async def _owner_link(self, person_id: uuid.UUID) -> tables.Link | None:
        return (await self.session.execute(select(tables.Link).where(
            tables.Link.table == 'person', tables.Link.objectid == person_id,
            tables.Link.scope == 'medical'))).scalars().first()

    async def concepts(self) -> dict[str, uuid.UUID]:
        """{code: Category.id} медицинских концептов (illness/symptom/...) — фронту для
        создания эпизодов/симптомов. Reference-данные (из seed_medical под корнем 'medical')."""
        return await medical_concepts(self.session)

    async def grants(self) -> list[dict]:
        """Слой B, дискавери: чужие медкарты, доступные мне по одобренным согласиям.
        [{link_id, key_id}] — эти параметры передаются в каждом запросе /me/*."""
        consents = (await self.session.execute(select(tables.Consent).where(
            tables.Consent.grantee == self.payload.sub,
            tables.Consent.scope == MEDICAL,
            tables.Consent.status == APPROVED,
            _until_alive()))).scalars().all()
        out = []
        for c in consents:
            owner = (await self.session.execute(select(tables.User.id).where(
                tables.User.person == c.objectid))).scalars().first()
            link = await self._owner_link(c.objectid)
            if owner is not None and link is not None:
                out.append({'link_id': link.id, 'key_id': f'patient:{owner}'})
        return out

    async def close_session(self) -> None:
        await get_cache().delete(self._key())

    async def _session_pseudonym(self) -> uuid.UUID:
        cached = await get_cache().get(self._key())
        if cached is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail='нет активной сессии доступа к медданным — откройте сессию')
        return uuid.UUID(cached)

    def _key(self) -> str:
        return f'{_SESSION_NS}:{self.payload.sub}'

    async def _resolve(self, link_id: uuid.UUID | None,
                       key_id: str | None) -> uuid.UUID:
        """Псевдоним: по (link_id, key_id) — разворот моста (Слой B, врач/близкий,
        без сессии), иначе из открытой owner-сессии (Слой A). ACL держит KeyService."""
        if link_id is None:
            return await self._session_pseudonym()
        if key_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail='при доступе по link_id нужен key_id')
        try:
            return await self.bridge.resolve(link_id, key_id, str(self.payload.sub))
        except PolicyError:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail='нет доступа к этому мосту (ACL ключа)')

    # --- данные: скоуп — псевдоним (сессии или моста) ---
    async def properties(self, category: uuid.UUID | None = None,
                         code: str | None = None,
                         link_id: uuid.UUID | None = None,
                         key_id: str | None = None) -> list[tables.Property]:
        pseudonym = await self._resolve(link_id, key_id)
        return await PropertyService(session=self.session).find(PropertyFilter(
            table='pseudonym', objectid=pseudonym, category=category, code=code))

    async def add_property(self, data: MedPropertyIn,
                           link_id: uuid.UUID | None = None,
                           key_id: str | None = None) -> tables.Property:
        pseudonym = await self._resolve(link_id, key_id)
        return await PropertyService(session=self.session).create(
            PropertyCreate(category=data.category, code=data.code, name=data.name,
                           table='pseudonym', objectid=pseudonym, value=data.value),
            creator=self.payload.sub)

    # --- эпизоды (болезнь/травма): Entity на псевдониме ---
    async def episodes(self, link_id: uuid.UUID | None = None,
                       key_id: str | None = None) -> list[tables.Entity]:
        pseudonym = await self._resolve(link_id, key_id)
        return list((await self.session.execute(select(tables.Entity).where(
            tables.Entity.table == 'pseudonym',
            tables.Entity.objectid == pseudonym))).scalars().all())

    async def open_episode(self, data: EpisodeIn, link_id: uuid.UUID | None = None,
                           key_id: str | None = None) -> tables.Entity:
        pseudonym = await self._resolve(link_id, key_id)
        # только эпизодный концепт (illness/injury — категория с FSM): иначе /state
        # и /transition дадут 400, а /assess отрапортует «полно» по пустому конфигу
        category = await self.session.get(tables.Category, data.category)
        if category is None or not (category.value or {}).get('fsm'):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail='категория не является эпизодным концептом (нет value.fsm)')
        return await EntityService(session=self.session).create(
            EntityCreate(category=data.category, code=data.code, name=data.name,
                         table='pseudonym', objectid=pseudonym),
            creator=self.payload.sub)

    async def _gate_episode(self, episode_id: uuid.UUID, link_id: uuid.UUID | None,
                            key_id: str | None) -> uuid.UUID:
        """Ворота эпизод-скоупа: эпизод обязан висеть на псевдониме вызывающего.
        Чужой/несуществующий -> 404 (не 403: не раскрываем существование чужого)."""
        pseudonym = await self._resolve(link_id, key_id)
        ep = await self.session.get(tables.Entity, episode_id)
        if ep is None or ep.table != 'pseudonym' or ep.objectid != pseudonym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='эпизод не найден')
        return pseudonym

    async def episode_properties(self, episode_id: uuid.UUID,
                                 category: uuid.UUID | None = None, code: str | None = None,
                                 link_id: uuid.UUID | None = None,
                                 key_id: str | None = None) -> list[tables.Property]:
        await self._gate_episode(episode_id, link_id, key_id)
        return await PropertyService(session=self.session).find(PropertyFilter(
            table='entity', objectid=episode_id, category=category, code=code))

    async def add_episode_property(self, episode_id: uuid.UUID, data: MedPropertyIn,
                                   link_id: uuid.UUID | None = None,
                                   key_id: str | None = None) -> tables.Property:
        await self._gate_episode(episode_id, link_id, key_id)
        return await PropertyService(session=self.session).create(
            PropertyCreate(category=data.category, code=data.code, name=data.name,
                           table='entity', objectid=episode_id, value=data.value),
            creator=self.payload.sub)

    async def episode_state(self, episode_id: uuid.UUID, link_id: uuid.UUID | None = None,
                            key_id: str | None = None) -> dict:
        await self._gate_episode(episode_id, link_id, key_id)
        return await FSMService(session=self.session).state('entity', episode_id)

    async def transition(self, episode_id: uuid.UUID, event: str,
                         link_id: uuid.UUID | None = None,
                         key_id: str | None = None) -> dict:
        await self._gate_episode(episode_id, link_id, key_id)
        return await FSMService(session=self.session).trigger(
            'entity', episode_id, event, creator=self.payload.sub)

    async def assess(self, episode_id: uuid.UUID, link_id: uuid.UUID | None = None,
                     key_id: str | None = None) -> dict:
        pseudonym = await self._gate_episode(episode_id, link_id, key_id)
        return await MedicalService(session=self.session).assess(pseudonym, episode_id)

    # --- интервью (сбор анамнеза по протоколу) — за теми же воротами эпизода ---
    async def interview_open(self, episode_id: uuid.UUID, link_id: uuid.UUID | None = None,
                             key_id: str | None = None) -> dict:
        pseudonym = await self._gate_episode(episode_id, link_id, key_id)
        return await InterviewService(session=self.session).open(
            episode_id, pseudonym, creator=self.payload.sub)

    async def interview_state(self, episode_id: uuid.UUID, link_id: uuid.UUID | None = None,
                              key_id: str | None = None) -> dict:
        pseudonym = await self._gate_episode(episode_id, link_id, key_id)
        return await InterviewService(session=self.session).state(episode_id, pseudonym)

    async def interview_answer(self, episode_id: uuid.UUID, body: dict,
                               link_id: uuid.UUID | None = None,
                               key_id: str | None = None) -> dict:
        pseudonym = await self._gate_episode(episode_id, link_id, key_id)
        return await InterviewService(session=self.session).answer(
            episode_id, pseudonym, body, creator=self.payload.sub)

    # --- документы/анализы: блоб (FileStore) + метаданные Data + очередь на ИИ-разбор ---
    async def _scope(self, episode_id: uuid.UUID | None,
                     link_id: uuid.UUID | None, key_id: str | None) -> tuple[str, uuid.UUID]:
        """Носитель документа: эпизод (за воротами) либо сам псевдоним."""
        if episode_id is not None:
            await self._gate_episode(episode_id, link_id, key_id)
            return 'entity', episode_id
        return 'pseudonym', await self._resolve(link_id, key_id)

    async def upload_document(self, content: bytes, name: str, code: str,
                              category: uuid.UUID | None = None, media_type: str = '',
                              episode_id: uuid.UUID | None = None,
                              link_id: uuid.UUID | None = None,
                              key_id: str | None = None) -> tables.Data:
        """Кладёт файл: блоб в FileStore + Data(метаданные, hash) на носителе +
        событие data.extract (ИИ-разбор). Блоб коммитится первым (put), поэтому к
        моменту разбора он уже существует; метаданные и событие — одной транзакцией."""
        table, objectid = await self._scope(episode_id, link_id, key_id)
        ref = await FileStore(session=self.session).put(content)
        data = tables.Data(category=category, code=code, name=name,
                           table=table, objectid=objectid,
                           hash=ref['hash'], algorithm=ref['algorithm'],
                           creator=self.payload.sub)
        self.session.add(data)
        request_extract(self.session, ref['hash'], table, objectid, media_type)
        await self.session.commit()
        return data

    async def documents(self, episode_id: uuid.UUID | None = None,
                        link_id: uuid.UUID | None = None,
                        key_id: str | None = None) -> list[tables.Data]:
        table, objectid = await self._scope(episode_id, link_id, key_id)
        return list((await self.session.execute(select(tables.Data).where(
            tables.Data.table == table, tables.Data.objectid == objectid))).scalars().all())
