"""Сбор анамнеза по протоколу (anamnez.md): конечный автомат с циклами уточнения.

Устройство — на существующем ядре, новых таблиц нет:
- интервью = Entity(category='interview') на эпизоде; его состояние ведёт
  штатный FSMService (Category.value['fsm'] категории interview);
- очередь симптомов и прогресс = Property(code='progress') на интервью
  (versioned_update — история опроса бесплатно);
- ответы write-through: симптом = Property(category=symptom) на эпизоде
  (слоты копятся в value['slots']), секции анамнеза жизни = Property на
  псевдониме — те же носители, что читает MedicalService.assess.

Протокол: главная жалоба -> цикл разбора каждого симптома (11 слотов;
слот 'associations' добавляет связанные симптомы в очередь) -> обзор систем
(ROS, 9 систем; позитив возвращает в цикл симптомов) -> анамнез жизни ->
проверка полноты (gaps) -> резюме -> подтверждение пациентом. Красный флаг
после любого ответа по симптому переводит интервью в 'emergency' (опрос
прерван); 'resume' продолжает после оказания помощи.

Клиент не дёргает переходы сам: единственная ручка answer(...) — сервер
решает переход по данным и всегда возвращает следующий вопрос.
"""
import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy import select, text

from ..database import db_helper
from ..medical_seed import SYMPTOM_SCHEMA, medical_concepts
from ..versioning import versioned_update
from .. import tables
from .fsm import FSMService
from .medical import MedicalService

PROGRESS = 'progress'
SUMMARY = 'summary'
# секции анамнеза жизни в порядке опроса (коды концептов; scope=patient)
HISTORY_SECTIONS = ['medication', 'allergy', 'chronic', 'surgery',
                    'heredity', 'social', 'risk_factor']
_SLOTS = [s['code'] for s in SYMPTOM_SCHEMA]
_LABELS = {s['code']: s['label'] for s in SYMPTOM_SCHEMA}


class InterviewService:
    """Драйвер опроса. Ворота эпизода (владение псевдонимом) — на вызывающем
    (MedAccessService), сюда приходят уже проверенные episode_id/pseudonym."""

    def __init__(self, session=Depends(db_helper.scoped_session_dependency)):
        self.session = session
        self.fsm = FSMService(session=session)

    # ------------------------------------------------------------------ #
    async def open(self, episode_id: uuid.UUID, pseudonym: uuid.UUID,
                   creator: uuid.UUID | None = None) -> dict:
        """Открывает (или возвращает уже открытое) интервью эпизода.

        Advisory-лок сериализует конкурентные открытия (двойной клик, двойной
        эффект StrictMode) — иначе гонка создаёт два интервью на эпизоде."""
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('interview:' || :eid))"),
            {'eid': str(episode_id)})
        row = await self._interview(episode_id)
        if row is None:
            cats = await medical_concepts(self.session)
            if 'interview' not in cats:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    detail="концепт 'interview' не найден — прогоните medical_seed")
            row = tables.Entity(category=cats['interview'], code='interview',
                                name='Опрос (анамнез)', table='entity',
                                objectid=episode_id, creator=creator)
            self.session.add(row)
            await self.session.flush()
            self.session.add(tables.Property(
                table='entity', objectid=row.id, code=PROGRESS, creator=creator,
                value={'queue': [], 'done': [], 'current': None, 'slot': 0,
                       'ros_idx': 0, 'ros': {}, 'section_idx': 0}))
            await self.session.commit()
        return await self.state(episode_id, pseudonym)

    async def state(self, episode_id: uuid.UUID, pseudonym: uuid.UUID) -> dict:
        """Текущее состояние интервью + следующий вопрос."""
        row = await self._require(episode_id)
        st = (await self.fsm.state('entity', row.id))['state']
        progress = (await self._progress(row.id)).value
        return await self._view(row, st, progress, episode_id, pseudonym)

    async def answer(self, episode_id: uuid.UUID, pseudonym: uuid.UUID,
                     body: dict, creator: uuid.UUID | None = None) -> dict:
        """Единственная точка ввода: маршрутизирует ответ по текущему состоянию,
        двигает автомат и возвращает следующий вопрос."""
        row = await self._require(episode_id)
        st = (await self.fsm.state('entity', row.id))['state']
        prow = await self._progress(row.id)
        progress = dict(prow.value)
        handler = getattr(self, f'_on_{st}', None)
        if handler is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=f"интервью в состоянии '{st}' — ответы не принимаются")
        st = await handler(row, progress, body, episode_id, pseudonym, creator)
        await versioned_update(self.session, tables.Property, prow.id, {'value': progress})
        await self.session.commit()
        return await self._view(row, st, progress, episode_id, pseudonym)

    # --- обработчики состояний: возвращают итоговое состояние ---------- #
    async def _on_complaint(self, row, progress, body, episode_id, pseudonym, creator):
        """Главная жалоба: {'symptom': code}. Очередь стартует с неё."""
        code = self._symptom_code(body)
        progress['queue'] = [code]
        progress['chief'] = code
        await self._next_symptom(row, progress, episode_id, creator)
        await self.fsm.trigger('entity', row.id, commit=False, event='begin_symptoms', creator=creator)
        return 'symptom'

    async def _on_symptom(self, row, progress, body, episode_id, pseudonym, creator):
        """Ответ на текущий слот: {'value': ...}; для associations value =
        [codes] — связанные симптомы уходят в очередь (рекурсивное дерево жалоб)."""
        if progress.get('current') is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail='нет текущего симптома')
        slot = _SLOTS[progress['slot']]
        value = body.get('value')
        if value is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"нужен ответ на слот '{slot}' (поле value)")
        if slot == 'severity' and not (isinstance(value, (int, float)) and 0 <= value <= 10):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail='интенсивность — число 0–10')
        sym = await self._symptom_property(episode_id, progress['current'])
        slots = {**sym.value.get('slots', {}), slot: value}
        await versioned_update(self.session, tables.Property, sym.id,
                               {'value': {**sym.value, 'slots': slots}})
        if slot == 'associations' and isinstance(value, list):
            known = set(progress['done']) | {progress['current']} | set(progress['queue'])
            progress['queue'] += [c for c in value if c not in known]

        # красные флаги — после каждого ответа; тревога прерывает опрос
        alerts = (await MedicalService(session=self.session)
                  .assess(pseudonym, episode_id))['alerts']
        if alerts:
            progress['alerts'] = alerts
            await self.fsm.trigger('entity', row.id, commit=False, event='red_flag', creator=creator)
            return 'emergency'

        progress['slot'] += 1
        if progress['slot'] < len(_SLOTS):
            return 'symptom'
        # симптом разобран: следующий из очереди, обзор систем либо (если ROS
        # уже пройден — возврат «да, ещё...» из резюме) сразу обратно к резюме
        progress['done'] = progress['done'] + [progress['current']]
        progress['current'], progress['slot'] = None, 0
        if progress['queue']:
            await self._next_symptom(row, progress, episode_id, creator)
            return 'symptom'
        if progress['ros_idx'] < len(await self._systems()):
            await self.fsm.trigger('entity', row.id, commit=False, event='to_ros', creator=creator)
            return 'ros'
        await self.fsm.trigger('entity', row.id, commit=False, event='to_summary', creator=creator)
        return 'summary'

    async def _on_ros(self, row, progress, body, episode_id, pseudonym, creator):
        """Обзор систем: {'positive': bool, 'symptoms': [codes]?}.
        Позитив добавляет симптомы в очередь и возвращает в цикл разбора."""
        systems = await self._systems()
        system = systems[progress['ros_idx']]
        if body.get('positive') and not body.get('symptoms'):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail='позитивная система требует кодов симптомов (symptoms)')
        found = [c for c in (body.get('symptoms') or []) if body.get('positive')]
        progress['ros'] = {**progress.get('ros', {}),
                           system: found if found else 'clear'}
        progress['ros_idx'] += 1
        # в цикл разбора возвращают только ещё не разобранные симптомы
        if new := [c for c in found if c not in progress['done']]:
            progress['queue'] += new
            await self._next_symptom(row, progress, episode_id, creator)
            await self.fsm.trigger('entity', row.id, commit=False, event='back_to_symptoms', creator=creator)
            return 'symptom'
        if progress['ros_idx'] < len(systems):
            return 'ros'
        await self.fsm.trigger('entity', row.id, commit=False, event='to_history', creator=creator)
        return 'history'

    async def _on_history(self, row, progress, body, episode_id, pseudonym, creator):
        """Секция анамнеза жизни: {'items': [...]} (пусто = «нет» — значимое
        отрицание) либо {'confirmed': true} — данные карты актуальны, секция
        не пересобирается (карта уже закрывает полноту)."""
        section = HISTORY_SECTIONS[progress['section_idx']]
        if body.get('confirmed'):
            if not await self._section_known(section, pseudonym):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail='подтверждать нечего — секция в карте пуста')
        else:
            await self._write_section(section, body.get('items') or [], pseudonym, creator)
        progress['section_idx'] += 1
        if progress['section_idx'] < len(HISTORY_SECTIONS):
            return 'history'
        await self.fsm.trigger('entity', row.id, commit=False, event='to_completeness', creator=creator)
        # проверка полноты сразу: пробелов нет — сразу к резюме
        return await self._maybe_summary(row, episode_id, pseudonym, creator)

    async def _on_completeness(self, row, progress, body, episode_id, pseudonym, creator):
        """Дозаполнение пробела: {'section': code, 'items': [...]}."""
        gaps = (await MedicalService(session=self.session)
                .assess(pseudonym, episode_id))['gaps']
        section = body.get('section')
        if section not in gaps:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f'ожидается заполнение пробела из {gaps}')
        await self._write_section(section, body.get('items') or [], pseudonym, creator)
        return await self._maybe_summary(row, episode_id, pseudonym, creator)

    async def _on_summary(self, row, progress, body, episode_id, pseudonym, creator):
        """Подтверждение пациентом: {'confirmed': true} либо
        {'more': [codes]} — «да, ещё...» возвращает в цикл симптомов."""
        more = [c for c in (body.get('more') or []) if c not in progress['done']]
        if more:
            progress['queue'] += more
            await self._next_symptom(row, progress, episode_id, creator)
            await self.fsm.trigger('entity', row.id, commit=False, event='more_symptoms', creator=creator)
            return 'symptom'
        if not body.get('confirmed'):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="нужно {'confirmed': true} либо {'more': [codes]}")
        # подтверждённое резюме фиксируется на эпизоде — итоговый документ опроса
        self.session.add(tables.Property(
            table='entity', objectid=episode_id, code=SUMMARY, creator=creator,
            value={**(await self._summary(episode_id, progress, pseudonym)),
                   'confirmed': True}))
        await self.fsm.trigger('entity', row.id, commit=False, event='confirm', creator=creator)
        return 'confirmed'

    async def _on_emergency(self, row, progress, body, episode_id, pseudonym, creator):
        """Экстренная ветка: опрос прерван. {'resume': true} — продолжить."""
        if not body.get('resume'):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail='интервью прервано красным флагом — экстренный протокол; '
                                       "продолжение: {'resume': true}")
        progress.pop('alerts', None)
        await self.fsm.trigger('entity', row.id, commit=False, event='resume', creator=creator)
        return 'symptom'

    # ------------------------------------------------------------------ #
    async def _view(self, row, st, progress, episode_id, pseudonym) -> dict:
        """Состояние + следующий вопрос (вычислим из состояния и прогресса)."""
        out = {'state': st, 'queue': progress.get('queue', []),
               'done': progress.get('done', [])}
        if st == 'complaint':
            out['question'] = {'ask': 'Главная жалоба', 'field': 'symptom'}
        elif st == 'symptom':
            slot = _SLOTS[progress['slot']]
            out['question'] = {'symptom': progress['current'], 'slot': slot,
                               'ask': _LABELS[slot], 'field': 'value'}
        elif st == 'ros':
            systems = await self._systems()
            out['question'] = {'system': systems[progress['ros_idx']],
                               'ask': 'Есть ли жалобы со стороны системы?',
                               'field': 'positive'}
        elif st == 'history':
            section = HISTORY_SECTIONS[progress['section_idx']]
            # known: что уже есть в карте — фронт предлагает подтвердить актуальность
            out['question'] = {'section': section, 'field': 'items',
                               'known': await self._section_known(section, pseudonym)}
        elif st == 'completeness':
            gaps = (await MedicalService(session=self.session)
                    .assess(pseudonym, episode_id))['gaps']
            out['question'] = {'gaps': gaps, 'field': 'items'}
        elif st == 'summary':
            out['summary'] = await self._summary(episode_id, progress, pseudonym)
            out['question'] = {'ask': 'Всё ли верно и полно?', 'field': 'confirmed'}
        elif st == 'emergency':
            out['alerts'] = progress.get('alerts', [])
            out['question'] = {'ask': 'ЭКСТРЕННЫЙ ПРОТОКОЛ: опрос прерван', 'field': 'resume'}
        return out

    async def _summary(self, episode_id, progress, pseudonym) -> dict:
        """Итоговое резюме: жалоба, симптомы со слотами, значимые отрицания, ROS."""
        cats = await medical_concepts(self.session)
        symptoms = (await self.session.execute(select(tables.Property).where(
            tables.Property.table == 'entity',
            tables.Property.objectid == episode_id,
            tables.Property.category == cats.get('symptom')))).scalars().all()
        return {
            'chief_complaint': progress.get('chief'),
            'symptoms': {p.code: p.value.get('slots', {}) for p in symptoms
                         if p.value.get('status') == 'present'},
            'negatives': [p.code for p in symptoms if p.value.get('status') == 'absent'],
            'ros': progress.get('ros', {}),
        }

    async def _maybe_summary(self, row, episode_id, pseudonym, creator) -> str:
        """completeness: пробелы есть — спрашиваем дальше, нет — к резюме."""
        gaps = (await MedicalService(session=self.session)
                .assess(pseudonym, episode_id))['gaps']
        if gaps:
            return 'completeness'
        await self.fsm.trigger('entity', row.id, commit=False, event='to_summary', creator=creator)
        return 'summary'

    async def _next_symptom(self, row, progress, episode_id, creator) -> None:
        """Берёт симптом из очереди и заводит под него Property на эпизоде."""
        progress['current'] = progress['queue'].pop(0)
        progress['slot'] = 0
        await self._symptom_property(episode_id, progress['current'], creator, create=True)

    async def _symptom_property(self, episode_id, code, creator=None,
                                create: bool = False) -> tables.Property:
        cats = await medical_concepts(self.session)
        row = (await self.session.execute(select(tables.Property).where(
            tables.Property.table == 'entity',
            tables.Property.objectid == episode_id,
            tables.Property.category == cats['symptom'],
            tables.Property.code == code))).scalars().first()
        if row is None and create:
            row = tables.Property(table='entity', objectid=episode_id,
                                  category=cats['symptom'], code=code, creator=creator,
                                  value={'status': 'present', 'source': 'interview',
                                         'slots': {}})
            self.session.add(row)
            await self.session.flush()
        if row is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=f"симптом '{code}' не заведён на эпизоде")
        return row

    async def _section_known(self, section: str, pseudonym) -> list[str]:
        """Коды активных записей секции в карте пациента (для подтверждения)."""
        cats = await medical_concepts(self.session)
        if section not in cats:
            return []
        rows = (await self.session.execute(select(tables.Property.code).where(
            tables.Property.table == 'pseudonym',
            tables.Property.objectid == pseudonym,
            tables.Property.category == cats[section]))).scalars().all()
        return list(rows)

    async def _write_section(self, section, items, pseudonym, creator) -> None:
        """Секция анамнеза жизни на псевдониме; пусто = явный «нет» (status absent)."""
        cats = await medical_concepts(self.session)
        if section not in cats:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"неизвестная секция '{section}'")
        if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail='items — список объектов')
        rows = items or [{'code': 'none', 'status': 'absent'}]
        for item in rows:
            code = item.get('code') or 'unspecified'
            self.session.add(tables.Property(
                table='pseudonym', objectid=pseudonym, category=cats[section],
                code=code, creator=creator,
                value={**item, 'source': 'interview'}))
        await self.session.flush()

    async def _systems(self) -> list[str]:
        """Коды систем ROS; порядок обхода — по коду (стабилен между запросами;
        сид создаёт всю партию одним моментом, begins не различает)."""
        cats = await medical_concepts(self.session)
        rows = (await self.session.execute(select(tables.Entity.code).where(
            tables.Entity.category == cats['system'])
            .order_by(tables.Entity.code))).scalars().all()
        return list(rows)

    def _symptom_code(self, body: dict) -> str:
        code = body.get('symptom')
        if not code or not isinstance(code, str):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail='нужен код симптома (поле symptom)')
        return code

    async def _interview(self, episode_id) -> tables.Entity | None:
        cats = await medical_concepts(self.session)
        # order_by: если дубль всё же возник (до advisory-лока) — детерминированно старейшее
        return (await self.session.execute(select(tables.Entity).where(
            tables.Entity.table == 'entity',
            tables.Entity.objectid == episode_id,
            tables.Entity.category == cats.get('interview'))
            .order_by(tables.Entity.begins, tables.Entity.id))).scalars().first()

    async def _require(self, episode_id) -> tables.Entity:
        row = await self._interview(episode_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail='интервью не открыто — POST /interview')
        return row

    async def _progress(self, interview_id) -> tables.Property:
        row = (await self.session.execute(select(tables.Property).where(
            tables.Property.table == 'entity',
            tables.Property.objectid == interview_id,
            tables.Property.code == PROGRESS))).scalars().first()
        if row is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail='прогресс интервью потерян')
        return row
