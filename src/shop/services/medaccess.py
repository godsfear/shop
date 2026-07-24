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
from ..medical_seed import (SEX_SPECIFIC, VITAL_SCOPES, medical_concepts,
                            symptom_slots)
from ..models.auth import TokenPayload
from ..models.entity import EntityCreate, EntityUpdate
from ..models.medical import (AnamnesisEdit, DiagnosisIn, EpisodeIn,
                              MedPropertyIn, MedPropertyOut, TreatmentIn)
from ..models.property import PropertyCreate, PropertyFilter
from ..services.auth import get_token_payload
from ..services.bridge import BridgeService
from ..services.consent import APPROVED, MEDICAL, _until_alive
from ..services.entity import EntityService
from ..services.evaluate import _upsert, request_evaluate, request_plan
from ..services.nutrition import NORM_CODE, request_meal_estimate, request_norm
from ..services.sleep import ASSESS_CODE, request_sleep_assess
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

    async def _owner_identity(self) -> tuple[int | None, str | None, dict | None]:
        """Возраст/пол/место жительства владельца из identity — только в
        owner-режиме (Слой B их не несёт). Идут контекстом в ИИ-оценки."""
        if self.link_id is not None:
            return None, None, None
        person = await self.session.get(tables.Person, await self._person_id())
        if person is None:
            return None, None, None
        today = datetime.date.today()
        bd = person.birthdate
        age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
        return age, ('м' if person.sex else 'ж'), (person.residence or None)

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
                                'events': {}, 'red_flags': {}, 'slots': {}}
        for c in cats:
            name = tr.get((c.id, 'name'), c.name)
            out['concepts'][c.code] = name
            v = c.value or {}
            # короткие подписи слотов анамнеза (развёрнутое резюме у эпизода)
            for s in (v.get('schema') or []):
                out['slots'][s['code']] = tr.get(
                    (c.id, f"slot_short.{s['code']}"), s.get('short', s['code']))
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
        if concept_code == 'vital':   # области применения: profile и/или diary
            for i in items:
                i['scopes'] = sorted(VITAL_SCOPES.get(i['code'], {'profile', 'diary'}))
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
        [{link_id, key_id, patient}] — параметры передаются в каждом запросе /me/*.

        patient — имя владельца карты: раскрывается ТОЛЬКО по одобренному
        согласию (до одобрения врач видит лишь код — иначе перебор кодов
        позволял бы узнавать имена)."""
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
            if owner is None or link is None:
                continue
            name = (await self.session.execute(select(tables.Person.name).where(
                tables.Person.id == c.objectid))).scalar_one_or_none() or {}
            patient = ' '.join(filter(None, [name.get('last'), name.get('first')]))
            out.append({'link_id': link.id, 'key_id': f'patient:{owner}',
                        'patient': patient or None})
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
        rows = await PropertyService(session=self.session).find(PropertyFilter(
            table='pseudonym', objectid=pseudonym, category=category, code=code))
        # /properties — стандартные факты «Моей карты». Ситуационные замеры
        # читаются только через /diary, хотя технически используют ту же
        # категорию vital и того же владельца-псевдоним.
        return [row for row in rows if (row.value or {}).get('source') != 'diary']

    async def add_property(self, data: MedPropertyIn) -> tables.Property:
        pseudonym = await self._resolve()
        conditions = [
            tables.Property.table == 'pseudonym',
            tables.Property.objectid == pseudonym,
            tables.Property.code == data.code,
            tables.Property.ends.is_(None),
            tables.Property.value['source'].astext.is_distinct_from('diary'),
        ]
        if data.category is None:
            conditions.append(tables.Property.category.is_(None))
        else:
            conditions.append(tables.Property.category == data.category)
        existing = (await self.session.execute(
            select(tables.Property.id).where(*conditions))).scalars().first()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail='property_exists')
        try:
            return await PropertyService(session=self.session).create(
                PropertyCreate(
                    category=data.category,
                    code=data.code,
                    name=data.name,
                    table='pseudonym',
                    objectid=pseudonym,
                    value={**data.value, 'source': 'profile'},
                ),
                creator=self.payload.sub,
            )
        except IntegrityError as exc:
            # Две конкурентные вставки могут одновременно пройти SELECT выше;
            # окончательный инвариант держит uq_property_active_profile.
            await self.session.rollback()
            if getattr(exc.orig, 'sqlstate', None) == '23505':
                raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                    detail='property_exists')
            raise

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
        source = (row.value or {}).get('source')
        value = {**value, 'source': source or 'profile'}
        updated = await versioned_update(self.session, tables.Property, row.id, {'value': value})
        await self.session.commit()
        return updated

    async def close_property(self, property_id: uuid.UUID) -> tables.Property:
        """Закрыть запись (перестал принимать лекарство и т.п.) — строка уходит в историю."""
        row = await self._gate_property(property_id)
        concepts = await medical_concepts(self.session)
        if (row.category == concepts.get('vital')
                and (row.value or {}).get('source') != 'diary'):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail='profile_vital_cannot_close')
        closed = await versioned_expire(self.session, tables.Property, row.id)
        await self.session.commit()
        return closed

    # --- общий дневник состояния: замеры и заметки на медкарте -----------------
    async def _diary_entries(self, pseudonym: uuid.UUID,
                             begins: datetime.datetime | None = None,
                             ends: datetime.datetime | None = None) -> list[tables.Property]:
        """Дневниковые события на карте; при границах — только внутри интервала."""
        cats = await medical_concepts(self.session)
        categories = [cats[c] for c in ('vital', 'note') if c in cats]
        if not categories:
            return []
        conditions = [
            tables.Property.table == 'pseudonym',
            tables.Property.objectid == pseudonym,
            tables.Property.category.in_(categories),
            tables.Property.value['source'].astext == 'diary',
        ]
        if begins is not None:
            conditions.append(tables.Property.begins >= begins)
        if ends is not None:
            conditions.append(tables.Property.begins <= ends)
        rows = await self.session.execute(select(tables.Property)
                                          .where(*conditions)
                                          .order_by(tables.Property.begins.desc()))
        return list(rows.scalars().all())

    async def diary(self) -> list[tables.Property]:
        """Общий для всех эпизодов дневник; активные записи — свежие сверху."""
        return await self._diary_entries(await self._resolve())

    async def add_diary_entry(self, data: MedPropertyIn) -> tables.Property:
        """Запись в общий дневник: только разрешённый замер или свободная заметка.

        Обычные /properties не годятся: замеры одного типа должны добавляться
        многократно, а не заменять друг друга как постоянный показатель карты.
        """
        pseudonym = await self._resolve()
        cats = await medical_concepts(self.session)
        vital, note = cats.get('vital'), cats.get('note')
        if data.category == vital:
            if data.code not in VITAL_SCOPES or 'diary' not in VITAL_SCOPES[data.code]:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    detail='diary_vital_invalid')
            if not str(data.value.get('value', '')).strip():
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    detail='diary_value_required')
        elif data.category == note:
            if not str(data.value.get('text', '')).strip():
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    detail='diary_note_required')
        else:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail='diary_category_invalid')
        prop = tables.Property(category=data.category, code=data.code, name=data.name,
                               table='pseudonym', objectid=pseudonym,
                               value={**data.value, 'source': 'diary'},
                               creator=self.payload.sub)
        self.session.add(prop)
        await self.session.commit()
        return prop

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

    async def _episode_window(self, episode_id: uuid.UUID) -> tuple[datetime.datetime, datetime.datetime | None]:
        """Интервал эпизода: конец берём из Entity или из финального FSM-состояния.

        Entity не закрывается при выздоровлении, поэтому для истории болезни
        окончанием является время входа в состояние без доступных переходов.
        """
        episode = await self.session.get(tables.Entity, episode_id)
        if episode is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='episode_not_found')
        ends = episode.ends
        if ends is None:
            state = await FSMService(session=self.session).state('entity', episode_id)
            if not state['available']:
                state_row = (await self.session.execute(select(tables.Property).where(
                    tables.Property.table == 'entity',
                    tables.Property.objectid == episode_id,
                    tables.Property.code == 'state',
                ))).scalars().first()
                if state_row is not None:
                    ends = state_row.begins
        return episode.begins, ends

    async def episode_diary(self, episode_id: uuid.UUID) -> list[tables.Property]:
        """Общий дневник, ограниченный сроком конкретного эпизода."""
        pseudonym = await self._gate_episode(episode_id)
        begins, ends = await self._episode_window(episode_id)
        return await self._diary_entries(
            pseudonym, begins, ends or datetime.datetime.now(datetime.timezone.utc))

    async def add_episode_property(self, episode_id: uuid.UUID, data: MedPropertyIn) -> tables.Property:
        await self._gate_episode(episode_id)
        return await PropertyService(session=self.session).create(
            PropertyCreate(category=data.category, code=data.code, name=data.name,
                           table='entity', objectid=episode_id, value=data.value),
            creator=self.payload.sub)

    async def close_episode_property(self, episode_id: uuid.UUID,
                                     property_id: uuid.UUID) -> tables.Property:
        """Удалить свойство эпизода (комментарий и т.п.) — ворота по эпизоду,
        плюс запись обязана висеть именно на нём (перебор id не трогает чужое)."""
        await self._gate_episode(episode_id)
        row = await self.session.get(tables.Property, property_id)
        if row is None or row.table != 'entity' or row.objectid != episode_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='record_not_found')
        closed = await versioned_expire(self.session, tables.Property, row.id)
        await self.session.commit()
        return closed

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
        age, sex, residence = await self._owner_identity()
        request_evaluate(self.session, episode_id, pseudonym, age, sex, residence, lang=self.lang)
        await self.session.commit()
        return {'queued': True}

    async def edit_anamnesis(self, episode_id: uuid.UUID, body: AnamnesisEdit) -> dict:
        """Правка ответа на слот симптома (опечатки) — ТОЛЬКО до диагноза:
        после него анамнез зафиксирован, диагноз ставился по этим данным.
        Подтверждённое резюме пересобирается из исправленных свойств."""
        pseudonym = await self._gate_episode(episode_id)
        fsm = FSMService(session=self.session)
        if (await fsm.state('entity', episode_id))['state'] != 'anamnesis':
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail='anamnesis_locked')
        if body.slot == 'associations' or body.slot not in symptom_slots(body.symptom):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f'slot_uneditable: {body.slot}')
        value = body.value
        if body.slot == 'severity':
            if not isinstance(value, (int, float)) or not 0 <= value <= 10:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail='severity_range')
        cats = await medical_concepts(self.session)
        sym = (await self.session.execute(select(tables.Property).where(
            tables.Property.table == 'entity',
            tables.Property.objectid == episode_id,
            tables.Property.category == cats.get('symptom'),
            tables.Property.code == body.symptom))).scalars().first()
        if sym is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f'symptom_not_found: {body.symptom}')
        slots = {**(sym.value.get('slots') or {}), body.slot: value}
        await versioned_update(self.session, tables.Property, sym.id,
                               {'value': {**sym.value, 'slots': slots}})
        # подтверждённое резюме — снимок слотов: пересобрать из исправленного
        summary = (await self.session.execute(select(tables.Property).where(
            tables.Property.table == 'entity',
            tables.Property.objectid == episode_id,
            tables.Property.code == 'summary'))).scalars().first()
        if summary is not None:
            svc = InterviewService(session=self.session, lang=self.lang)
            row = await svc._interview(episode_id)
            progress = (await svc._progress(row.id)).value
            rebuilt = await svc._summary(episode_id, progress, pseudonym)
            await versioned_update(self.session, tables.Property, summary.id,
                                   {'value': {**rebuilt, 'confirmed': True}})
        await self.session.commit()
        # красные флаги перепроверяются по исправленным данным — правка могла
        # как поднять тревогу, так и снять её; фронт показывает в «Стоит дополнить»
        alerts = (await MedicalService(session=self.session)
                  .assess(pseudonym, episode_id))['alerts']
        return {'ok': True, 'alerts': alerts}

    async def set_diagnosis(self, episode_id: uuid.UUID, body: DiagnosisIn) -> dict:
        """Установить диагноз: свойство + переход FSM + план назначений от ИИ —
        одной транзакцией. Повторная установка обновляет диагноз (версионно)
        и пересчитывает план."""
        pseudonym = await self._gate_episode(episode_id)
        await _upsert(self.session, episode_id, 'diagnosis',
                      {'text': body.text, 'source': body.source})
        fsm = FSMService(session=self.session)
        st = await fsm.state('entity', episode_id)
        if 'diagnose' in st['available']:
            await fsm.trigger('entity', episode_id, 'diagnose',
                              creator=self.payload.sub, commit=False)
        request_plan(self.session, episode_id, pseudonym, body.text, lang=self.lang)
        await self.session.commit()
        return {'queued': True}

    async def start_treatment(self, episode_id: uuid.UUID, body: TreatmentIn) -> dict:
        """Начать лечение: зафиксировать назначения (выбор из плана ИИ и/или
        свои) + переход FSM одной транзакцией."""
        await self._gate_episode(episode_id)
        await _upsert(self.session, episode_id, 'treatment',
                      {'items': [i.model_dump(exclude_none=True) for i in body.items],
                       'source': 'patient'})
        fsm = FSMService(session=self.session)
        st = await fsm.state('entity', episode_id)
        if 'treat' in st['available']:
            await fsm.trigger('entity', episode_id, 'treat',
                              creator=self.payload.sub, commit=False)
        await self.session.commit()
        return {'ok': True}

    # --- питание: приёмы пищи (оценка ИИ) и суточная норма -----------------
    async def add_meal(self, day: str, desc: str,
                       photo: bytes | None, media_type: str) -> tables.Property:
        """Приём пищи: запись со status='estimating' + задача оценки в очередь.
        day — локальная дата клиента (YYYY-MM-DD): сутки считает пользователь,
        не UTC. Фото — транзитный блоб, консумер удалит после оценки."""
        pseudonym = await self._resolve()
        cats = await medical_concepts(self.session)
        if 'meal' not in cats:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail='seed_missing: meal')
        prop = tables.Property(
            table='pseudonym', objectid=pseudonym, category=cats['meal'],
            code='meal', creator=self.payload.sub,
            value={'desc': desc, 'day': day, 'status': 'estimating',
                   'source': 'ai',
                   'at': datetime.datetime.now(datetime.timezone.utc)
                         .isoformat(timespec='minutes')})
        self.session.add(prop)
        await self.session.flush()
        blob_hash = None
        if photo:
            blob_hash = (await FileStore(session=self.session).put(photo))['hash']
        request_meal_estimate(self.session, prop.id, blob_hash,
                              media_type or None, desc, lang=self.lang)
        await self.session.commit()
        return prop

    async def nutrition(self, day: str) -> dict:
        """Сводка дня: норма + приёмы пищи + суммы. Норма пересчитывается
        лениво: запрошен день новее её даты — ставим задачу ИИ, а пока отдаём
        прежние цифры со status='pending' (маркер же защищает от повторных
        постановок при поллинге)."""
        pseudonym = await self._resolve()
        cats = await medical_concepts(self.session)
        meals = [p for p in (await self.session.execute(select(tables.Property).where(
            tables.Property.table == 'pseudonym',
            tables.Property.objectid == pseudonym,
            tables.Property.category == cats.get('meal')))).scalars().all()
            if (p.value or {}).get('day') == day]
        meals.sort(key=lambda p: p.begins, reverse=True)

        norm = (await self.session.execute(select(tables.Property).where(
            tables.Property.table == 'pseudonym',
            tables.Property.objectid == pseudonym,
            tables.Property.code == NORM_CODE))).scalars().first()
        if norm is None or (norm.value or {}).get('date', '') < day:
            age, sex, residence = await self._owner_identity()
            request_norm(self.session, pseudonym, day, age, sex, residence, lang=self.lang)
            # маркер pending: прежние цифры остаются видимыми до пересчёта
            pend = {**(norm.value if norm else {}), 'date': day, 'status': 'pending'}
            if norm is not None:
                norm = await versioned_update(self.session, tables.Property,
                                              norm.id, {'value': pend})
            else:
                norm = tables.Property(table='pseudonym', objectid=pseudonym,
                                       code=NORM_CODE, value=pend)
                self.session.add(norm)
            await self.session.commit()

        done = [p.value for p in meals if p.value.get('status') == 'done']
        totals = {k: round(sum(float((v.get('totals') or {}).get(k) or 0)
                               for v in done), 1)
                  for k in ('kcal', 'protein', 'fat', 'carbs')}
        out_meal = MedPropertyOut.model_validate
        return {'day': day, 'norm': norm.value if norm else None,
                'meals': [out_meal(p) for p in meals], 'totals': totals}

    # --- сон: журнал ночей + оценка ИИ за период (один раз при записи) --------
    async def add_sleep(self, day: str, value: dict) -> tables.Property:
        """Запись ночи (Property на псевдониме) + постановка оценки сна за период.
        Оценку пересчитываем при каждой записи; прежний текст висит со
        status='pending' до готовности (маркер защищает от дублей при поллинге)."""
        pseudonym = await self._resolve()
        cats = await medical_concepts(self.session)
        if 'sleep' not in cats:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail='seed_missing: sleep')
        prop = tables.Property(table='pseudonym', objectid=pseudonym,
                               category=cats['sleep'], code=f'sleep-{day}-{uuid.uuid4()}',
                               name=day, value={**value, 'date': day})
        self.session.add(prop)
        await self.session.flush()
        age, sex, residence = await self._owner_identity()
        request_sleep_assess(self.session, pseudonym, age, sex, residence, lang=self.lang)
        assess = (await self.session.execute(select(tables.Property).where(
            tables.Property.table == 'pseudonym',
            tables.Property.objectid == pseudonym,
            tables.Property.code == ASSESS_CODE))).scalars().first()
        pend = {**(assess.value if assess else {}), 'status': 'pending'}
        if assess is not None:
            await versioned_update(self.session, tables.Property, assess.id, {'value': pend})
        else:
            self.session.add(tables.Property(table='pseudonym', objectid=pseudonym,
                                             code=ASSESS_CODE, value=pend))
        await self.session.commit()
        return prop

    async def sleep_journal(self) -> dict:
        """Журнал ночей (свежие сверху) + последняя оценка сна ИИ."""
        pseudonym = await self._resolve()
        cats = await medical_concepts(self.session)
        entries = (await self.session.execute(select(tables.Property).where(
            tables.Property.table == 'pseudonym',
            tables.Property.objectid == pseudonym,
            tables.Property.category == cats.get('sleep'))
            .order_by(tables.Property.begins.desc()))).scalars().all()
        assess = (await self.session.execute(select(tables.Property).where(
            tables.Property.table == 'pseudonym',
            tables.Property.objectid == pseudonym,
            tables.Property.code == ASSESS_CODE))).scalars().first()
        out = MedPropertyOut.model_validate
        return {'entries': [out(p) for p in entries],
                'assessment': assess.value if assess else None}

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

    async def document_content(self, data_id: uuid.UUID) -> tuple[bytes, str, str]:
        """Содержимое документа: (байты, mime, имя).

        Ворота — принадлежность носителю, а НЕ только id документа: иначе
        перебор id отдавал бы чужие файлы. Эпизод проверяем _gate_episode
        (владение псевдонимом), документы на псевдониме — сверкой скоупа."""
        row = await self.session.get(tables.Data, data_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail='record_not_found')
        if row.table == 'entity':
            await self._gate_episode(row.objectid)
        elif row.objectid != await self._resolve():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail='record_not_found')
        blob = await FileStore(session=self.session).get(row.hash)
        if blob is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail='record_not_found')
        return blob, row.media_type or 'application/octet-stream', row.name or row.code

    async def documents(self, episode_id: uuid.UUID | None = None) -> list[tables.Data]:
        table, objectid = await self._scope(episode_id)
        return list((await self.session.execute(select(tables.Data).where(
            tables.Data.table == table, tables.Data.objectid == objectid))).scalars().all())
