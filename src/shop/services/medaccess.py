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
import datetime
import uuid

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from ..versioning import versioned_expire, versioned_update

from ..cache import get_cache
from ..database import db_helper
from ..keyservice import KeyServiceError, PolicyError
from ..medical_seed import SEX_SPECIFIC, medical_concepts
from ..models.auth import TokenPayload
from ..models.entity import EntityCreate, EntityUpdate
from ..models.medical import EpisodeIn, MedPropertyIn
from ..models.property import PropertyCreate, PropertyFilter
from ..services.auth import get_token_payload
from ..services.bridge import BridgeService
from ..services.consent import APPROVED, MEDICAL, _until_alive
from ..services.entity import EntityService
from ..services.evaluate import request_evaluate
from ..services.extract import request_extract
from ..services.files import FileStore
from ..services.fsm import FSMService
from ..services.interview import InterviewService
from ..services.medical import MedicalService
from ..services.property import PropertyService
from ..services.translation import BASE_LANG, primary_language, resolve
from ..settings import settings
from .. import tables

_SESSION_NS = 'medsession'


async def enroll_patient(session, keys, user_id: uuid.UUID, person_id: uuid.UUID) -> None:
    """Выпуск медключей и моста пациента; идемпотентно.

    Вызывается при регистрации (ключи выпускаются каждому сразу — решение
    владельца) и из /me/enroll (страховка для учёток, созданных до этого).
    MVP-стенд-ин клиентской крипты: ceiling — owner-DEK на клиенте."""
    existing = (await session.execute(select(tables.Link).where(
        tables.Link.table == 'person', tables.Link.objectid == person_id,
        tables.Link.scope == 'medical'))).scalars().first()
    if existing is not None:
        return                                      # уже выпущен
    patient_key = f'patient:{user_id}'
    for kid in ('escrow', patient_key):             # escrow — общесистемный (break-glass)
        try:
            await keys.create_key(kid)
        except KeyServiceError:
            pass                                    # ключ уже существует
    await keys.grant(patient_key, str(user_id))
    try:
        await BridgeService(session=session, keys=keys).create_link(
            'person', person_id, 'medical', groups={patient_key: person_id})
    except IntegrityError:
        # конкурентный выпуск уже создал мост (uq_link_subject_scope) — идемпотентно
        await session.rollback()
    # re-sync: медицинские согласия, одобренные ДО выпуска ключа, догрантиваются
    grantees = (await session.execute(select(tables.Consent.grantee).where(
        tables.Consent.table == 'person', tables.Consent.objectid == person_id,
        tables.Consent.scope == MEDICAL, tables.Consent.status == APPROVED,
        _until_alive()))).scalars().all()
    for grantee in grantees:
        await keys.grant(patient_key, str(grantee))


class MedAccessService:
    """Сессия + доступ к медданным пациента (по псевдониму), НЕ сущность-CRUD.

    Работает со скоупом псевдонима (Pseudonym, «пациент №...»), а не с Person:
    личность и медданные развязаны псевдонимизацией, ключом Person здесь быть
    не должно."""

    def __init__(self, session=Depends(db_helper.scoped_session_dependency),
                 bridge: BridgeService = Depends(),
                 payload: TokenPayload = Depends(get_token_payload),
                 link_id: Annotated[uuid.UUID | None, Query()] = None,
                 key_id: Annotated[str | None, Query()] = None,
                 accept_language: Annotated[str | None, Header()] = None):
        self.session = session
        self.bridge = bridge
        self.payload = payload
        # язык ответов (подписи, вопросы, ИИ): Accept-Language -> первичный тег
        self.lang = primary_language(accept_language)
        # Слой B (врач/близкий): link_id/key_id — query-параметры КАЖДОГО запроса,
        # резолвятся в _resolve; продевать их через сигнатуры методов не нужно
        self.link_id = link_id
        self.key_id = key_id

    # --- онбординг: выпуск моста (штатно происходит при регистрации) ---
    async def enroll(self) -> None:
        """Идемпотентный довыпуск ключей — для учёток, созданных до автовыпуска."""
        await enroll_patient(self.session, self.bridge.keys,
                             self.payload.sub, await self._person_id())

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
                                detail='enroll_required')
        try:
            pseudonym = await self.bridge.resolve(link.id, self._patient_key(),
                                                  str(self.payload.sub))
        except (PolicyError, KeyServiceError):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail='own_bridge_denied')
        # Redis здесь — хранилище сессии, а не кэш: молчаливый no-op означал бы
        # 200 «сессия открыта» и сплошные 401 на каждом следующем запросе
        if not await get_cache().set(self._key(), str(pseudonym), settings.medsession_ttl_s):
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail='session_store_unavailable')
        return settings.medsession_ttl_s

    def _patient_key(self) -> str:
        return f'patient:{self.payload.sub}'

    async def _person_id(self) -> uuid.UUID:
        person = (await self.session.execute(select(tables.User.person).where(
            tables.User.id == self.payload.sub))).scalar_one_or_none()
        if person is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail='user_not_found')
        return person

    async def _owner_link(self, person_id: uuid.UUID) -> tables.Link | None:
        return (await self.session.execute(select(tables.Link).where(
            tables.Link.table == 'person', tables.Link.objectid == person_id,
            tables.Link.scope == 'medical'))).scalars().first()

    async def concepts(self) -> dict[str, uuid.UUID]:
        """{code: Category.id} медицинских концептов (illness/symptom/...) — фронту для
        создания эпизодов/симптомов. Reference-данные (из seed_medical под корнем 'medical')."""
        return await medical_concepts(self.session)

    async def meta(self) -> dict:
        """Подписи доменных кодов для UI: {concepts, kinds, states, events, red_flags},
        каждый — {код: подпись}. Единый источник — справочное дерево (сид):
        правка подписи в БД видна фронту без правки кода.
        kinds — концепты-эпизоды (определяют fsm+required): чипы «болезнь/травма».
        Язык — self.lang (Accept-Language): переводы из Translation поверх
        базовых (ru) подписей, фолбэк lang -> en -> базовое."""
        ids = list((await medical_concepts(self.session)).values())
        cats = (await self.session.execute(select(tables.Category)
                .where(tables.Category.id.in_(ids)))).scalars()
        tr = {} if self.lang == BASE_LANG else \
            await resolve(self.session, 'category', ids, self.lang)
        out: dict[str, dict] = {'concepts': {}, 'kinds': {}, 'states': {},
                                'events': {}, 'red_flags': {}}
        for c in cats:
            name = tr.get((c.id, 'name'), c.name)
            out['concepts'][c.code] = name
            v = c.value or {}
            fsm = v.get('fsm') or {}
            if fsm and v.get('required'):
                out['kinds'][c.code] = name
            for prefix, group, labels in (
                    ('state', 'states', fsm.get('state_labels')),
                    ('event', 'events', fsm.get('event_labels')),
                    ('red_flag', 'red_flags', v.get('red_flag_labels'))):
                for code, base in (labels or {}).items():
                    out[group][code] = tr.get((c.id, f'{prefix}.{code}'), base)
        return out

    async def dictionary(self, concept_code: str) -> list[dict]:
        """Справочник элементов концепта (symptom/system/medication/...) — reference,
        ворот не требует: чипы выбора в интервью и формах."""
        cid = (await medical_concepts(self.session)).get(concept_code)
        if cid is None:
            return []
        rows = (await self.session.execute(
            select(tables.Entity.id, tables.Entity.code, tables.Entity.name)
            .where(tables.Entity.category == cid)
            .order_by(tables.Entity.name))).all()
        tr = {} if self.lang == BASE_LANG else \
            await resolve(self.session, 'entity', [r[0] for r in rows], self.lang)
        items = [{'code': code, 'name': tr.get((eid, 'name'), name)}
                 for eid, code, name in rows]
        # owner-режим: скрыть не соответствующее полу владельца (кесарево у
        # мужчины). Слой B (link_id) — пол пациента не раскрыт, показываем всё.
        if self.link_id is None:
            sex = (await self.session.execute(
                select(tables.Person.sex)
                .join(tables.User, tables.User.person == tables.Person.id)
                .where(tables.User.id == self.payload.sub))).scalar_one_or_none()
            if sex is not None:
                items = [i for i in items if SEX_SPECIFIC.get(i['code'], sex) == sex]
        # порядок — по подписи на языке ответа (для system порядок обхода
        # задаёт бэк интервью, здесь только представление)
        return sorted(items, key=lambda i: i['name'])

    async def access_log(self, limit: int = 100) -> list[dict]:
        """Журнал доступов к моей карте — владельцу для прозрачности.

        Источник — append-only аудит ключевого сервиса (KeyAudit, хеш-цепочка):
        развороты ключа patient:{sub}, отказы и break-glass. actor = user id;
        имя не раскрываем (каталог закрыт) — сопоставляем с reason согласий."""
        key = self._patient_key()
        events = ('key.unwrap', 'key.unwrap.denied', 'breakglass.execute')
        rows = (await self.session.execute(
            select(tables.KeyAudit)
            .where(tables.KeyAudit.event.in_(events),
                   tables.KeyAudit.data['key_id'].astext == key)
            .order_by(tables.KeyAudit.seq.desc())
            .limit(limit))).scalars().all()
        # actor -> представление из согласий (действующих и прошлых версий не ищем — MVP)
        reasons = {str(c.grantee): c.reason for c in (await self.session.execute(
            select(tables.Consent).where(
                tables.Consent.table == 'person',
                tables.Consent.scope == MEDICAL))).scalars().all()}
        me = str(self.payload.sub)
        out = []
        for r in rows:
            actor = r.data.get('actor')
            out.append({
                'at': r.ts, 'event': r.event,
                'who': 'вы' if actor == me else
                       (reasons.get(actor) or f'доступ …{(actor or "")[-6:]}'),
            })
        return out

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
                                detail='medsession_required')
        return uuid.UUID(cached)

    def _key(self) -> str:
        return f'{_SESSION_NS}:{self.payload.sub}'

    async def _resolve(self) -> uuid.UUID:
        """Псевдоним: по (link_id, key_id) — разворот моста (Слой B, врач/близкий,
        без сессии), иначе из открытой owner-сессии (Слой A). ACL держит KeyService."""
        if self.link_id is None:
            return await self._session_pseudonym()
        if self.key_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail='key_id_required')
        try:
            return await self.bridge.resolve(self.link_id, self.key_id, str(self.payload.sub))
        except PolicyError:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail='bridge_denied')

    # --- данные: скоуп — псевдоним (сессии или моста) ---
    async def properties(self, category: uuid.UUID | None = None,
                         code: str | None = None) -> list[tables.Property]:
        pseudonym = await self._resolve()
        return await PropertyService(session=self.session).find(PropertyFilter(
            table='pseudonym', objectid=pseudonym, category=category, code=code))

    async def add_property(self, data: MedPropertyIn) -> tables.Property:
        pseudonym = await self._resolve()
        return await PropertyService(session=self.session).create(
            PropertyCreate(category=data.category, code=data.code, name=data.name,
                           table='pseudonym', objectid=pseudonym, value=data.value),
            creator=self.payload.sub)

    async def _gate_property(self, property_id: uuid.UUID) -> tables.Property:
        """Запись обязана висеть на псевдониме вызывающего (чужая/нет -> 404)."""
        pseudonym = await self._resolve()
        row = await self.session.get(tables.Property, property_id)
        if row is None or row.table != 'pseudonym' or row.objectid != pseudonym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='record_not_found')
        return row

    async def update_property(self, property_id: uuid.UUID, value: dict) -> tables.Property:
        """Новое значение записи (рост, дозировка...); версия-копия — история бесплатно."""
        row = await self._gate_property(property_id)
        updated = await versioned_update(self.session, tables.Property, row.id, {'value': value})
        await self.session.commit()
        return updated

    async def close_property(self, property_id: uuid.UUID) -> tables.Property:
        """Закрыть запись (перестал принимать лекарство и т.п.) — строка уходит в историю."""
        row = await self._gate_property(property_id)
        closed = await versioned_expire(self.session, tables.Property, row.id)
        await self.session.commit()
        return closed

    async def property_history(self, property_id: uuid.UUID) -> list[tables.Property]:
        """Версии записи (история значений показателя), от старых к новым."""
        row = await self._gate_property(property_id)
        q = (select(tables.Property)
             .where(or_(tables.Property.id == row.id,
                        tables.Property.version_of == row.id))
             .order_by(tables.Property.begins)
             .execution_options(include_expired=True))
        return list((await self.session.execute(q)).scalars().all())

    # --- эпизоды (болезнь/травма): Entity на псевдониме ---
    async def episodes(self) -> list[tables.Entity]:
        pseudonym = await self._resolve()
        return list((await self.session.execute(select(tables.Entity).where(
            tables.Entity.table == 'pseudonym',
            tables.Entity.objectid == pseudonym))).scalars().all())

    async def open_episode(self, data: EpisodeIn) -> tables.Entity:
        pseudonym = await self._resolve()
        # только эпизодный концепт (illness/injury — категория с FSM): иначе /state
        # и /transition дадут 400, а /assess отрапортует «полно» по пустому конфигу
        category = await self.session.get(tables.Category, data.category)
        if category is None or not (category.value or {}).get('fsm'):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail='not_episode_concept')
        return await EntityService(session=self.session).create(
            EntityCreate(category=data.category, code=data.code, name=data.name,
                         table='pseudonym', objectid=pseudonym),
            creator=self.payload.sub)

    async def _gate_episode(self, episode_id: uuid.UUID) -> uuid.UUID:
        """Ворота эпизод-скоупа: эпизод обязан висеть на псевдониме вызывающего.
        Чужой/несуществующий -> 404 (не 403: не раскрываем существование чужого)."""
        pseudonym = await self._resolve()
        ep = await self.session.get(tables.Entity, episode_id)
        if ep is None or ep.table != 'pseudonym' or ep.objectid != pseudonym:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='episode_not_found')
        return pseudonym

    async def episode_properties(self, episode_id: uuid.UUID,
                                 category: uuid.UUID | None = None, code: str | None = None) -> list[tables.Property]:
        await self._gate_episode(episode_id)
        return await PropertyService(session=self.session).find(PropertyFilter(
            table='entity', objectid=episode_id, category=category, code=code))

    async def add_episode_property(self, episode_id: uuid.UUID, data: MedPropertyIn) -> tables.Property:
        await self._gate_episode(episode_id)
        return await PropertyService(session=self.session).create(
            PropertyCreate(category=data.category, code=data.code, name=data.name,
                           table='entity', objectid=episode_id, value=data.value),
            creator=self.payload.sub)

    async def episode(self, episode_id: uuid.UUID) -> tables.Entity:
        await self._gate_episode(episode_id)
        return await self.session.get(tables.Entity, episode_id)

    async def rename_episode(self, episode_id: uuid.UUID, name: str) -> tables.Entity:
        """Название даёт диагноз, не создание: эпизод открывается жалобой."""
        await self._gate_episode(episode_id)
        return await EntityService(session=self.session).update(
            episode_id, EntityUpdate(name=name))

    async def episode_history(self, episode_id: uuid.UUID) -> list[dict]:
        """Журнал переходов: закрытые строки состояния (темпоральная модель)."""
        await self._gate_episode(episode_id)
        rows = await FSMService(session=self.session).history('entity', episode_id)
        return [{'state': r.value.get('state'), 'event': r.value.get('event'),
                 'begins': r.begins, 'ends': r.ends} for r in rows]

    async def episode_state(self, episode_id: uuid.UUID) -> dict:
        await self._gate_episode(episode_id)
        return await FSMService(session=self.session).state('entity', episode_id)

    async def transition(self, episode_id: uuid.UUID, event: str) -> dict:
        await self._gate_episode(episode_id)
        return await FSMService(session=self.session).trigger(
            'entity', episode_id, event, creator=self.payload.sub)

    async def assess(self, episode_id: uuid.UUID) -> dict:
        pseudonym = await self._gate_episode(episode_id)
        return await MedicalService(session=self.session).assess(pseudonym, episode_id)

    async def evaluate(self, episode_id: uuid.UUID) -> dict:
        """Поставить ИИ-оценку эпизода в очередь. Возраст/пол — только когда
        вызывает владелец (identity-чтение самого себя); Слой B их не несёт."""
        pseudonym = await self._gate_episode(episode_id)
        age = sex = None
        if self.link_id is None:
            person = await self.session.get(tables.Person, await self._person_id())
            if person is not None:
                today = datetime.date.today()
                bd = person.birthdate
                age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
                sex = 'м' if person.sex else 'ж'
        request_evaluate(self.session, episode_id, pseudonym, age, sex, lang=self.lang)
        await self.session.commit()
        return {'queued': True}

    # --- интервью (сбор анамнеза по протоколу) — за теми же воротами эпизода ---
    async def interview_open(self, episode_id: uuid.UUID) -> dict:
        pseudonym = await self._gate_episode(episode_id)
        return await InterviewService(session=self.session, lang=self.lang).open(
            episode_id, pseudonym, creator=self.payload.sub)

    async def interview_state(self, episode_id: uuid.UUID) -> dict:
        pseudonym = await self._gate_episode(episode_id)
        return await InterviewService(session=self.session, lang=self.lang).state(episode_id, pseudonym)

    async def interview_answer(self, episode_id: uuid.UUID, body: dict) -> dict:
        pseudonym = await self._gate_episode(episode_id)
        return await InterviewService(session=self.session, lang=self.lang).answer(
            episode_id, pseudonym, body, creator=self.payload.sub)

    # --- документы/анализы: блоб (FileStore) + метаданные Data + очередь на ИИ-разбор ---
    async def _scope(self, episode_id: uuid.UUID | None) -> tuple[str, uuid.UUID]:
        """Носитель документа: эпизод (за воротами) либо сам псевдоним."""
        if episode_id is not None:
            await self._gate_episode(episode_id)
            return 'entity', episode_id
        return 'pseudonym', await self._resolve()

    async def upload_document(self, content: bytes, name: str, code: str,
                              category: uuid.UUID | None = None, media_type: str = '',
                              episode_id: uuid.UUID | None = None) -> tables.Data:
        """Кладёт файл: блоб (FileStore) + Data(метаданные, hash). При
        settings.auto_extract — ещё и событие data.extract (ИИ-разбор в
        структурные находки); по умолчанию off — диагноз читает оригинал."""
        table, objectid = await self._scope(episode_id)
        ref = await FileStore(session=self.session).put(content)
        data = tables.Data(category=category, code=code, name=name,
                           table=table, objectid=objectid,
                           hash=ref['hash'], algorithm=ref['algorithm'],
                           media_type=media_type or None,   # для мультимодального диагноза
                           creator=self.payload.sub)
        self.session.add(data)
        if settings.auto_extract:
            request_extract(self.session, ref['hash'], table, objectid, media_type)
        await self.session.commit()
        return data

    async def documents(self, episode_id: uuid.UUID | None = None) -> list[tables.Data]:
        table, objectid = await self._scope(episode_id)
        return list((await self.session.execute(select(tables.Data).where(
            tables.Data.table == table, tables.Data.objectid == objectid))).scalars().all())
