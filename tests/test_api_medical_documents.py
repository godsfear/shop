"""API `/me/documents`: загрузка файла -> блоб (FileStore) + Data(метаданные) +
outbox data.extract -> Property(source='ai'). Замыкает ИИ-конвейер на HTTP-слой.
Форсит заглушку экстрактора (не ходит в Gemini). Требует Redis (сессия).

Отдельно закрыты два случая с ценой ошибки в медданных:
- направления и рецепты («на руки» пациенту) НЕ попадают в бандл для ИИ;
- содержимое документа гейтится по носителю, а не по id — перебор id
  не отдаёт чужие файлы."""
import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import text, select, func
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.keyservice import DbKeyService
from shop.medical_seed import seed_medical
from shop.models.auth import TokenPayload
from shop.models.medical import EpisodeIn, DataOut
from shop.models.user import UserCreate, Contact
from shop.services.bridge import BridgeService
from shop.services.evaluate import _episode_docs
from shop.services.files import FileStore
from shop.services.medaccess import MedAccessService
from shop.services.user import UserService
from shop.settings import settings
from conftest import drain

URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'


def _svc(s, ks, payload):
    return MedAccessService(session=s, bridge=BridgeService(session=s, keys=ks), payload=payload)


async def test_main():
    settings.google_api_key = None                # держим заглушку: без сети/Gemini
    settings.auto_extract = True                  # тест проверяет авто-разбор при загрузке
    eng = create_async_engine(URI, poolclass=NullPool)
    async with eng.begin() as conn:
        await conn.execute(text('DROP SCHEMA public CASCADE'))
        await conn.execute(text('CREATE SCHEMA public'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
        await conn.run_sync(t.Root.metadata.create_all)
    Sess = async_sessionmaker(eng, expire_on_commit=False)

    async with Sess() as s:
        ids = await seed_medical(s)
    async with Sess() as s:
        country = t.Country(iso2='ru', iso3='rus', name='Russia')
        s.add(country); await s.flush()
        place = t.Place(code='msk', name='Москва', country=country.id)
        s.add(place); await s.commit()
        place_id = place.id
    async with Sess() as s:
        person = t.Person(name={'last': 'Иванов'}, sex=True,
                          birthdate=datetime.date(1980, 5, 1), birth_place=place_id)
        s.add(person); await s.commit()
        person_id = person.id
        user = await UserService(session=s).create(UserCreate(
            person=person_id, contact=Contact(email='p@x.com'), password='correct-horse'))
        user_id = user.id

    ks = DbKeyService(Sess)
    await ks.create_key('escrow')
    key_id = f'patient:{user_id}'
    await ks.create_key(key_id); await ks.grant(key_id, str(user_id))
    async with Sess() as s:
        link, pseudonym_id = await BridgeService(session=s, keys=ks).create_link(
            'person', person_id, 'medical', groups={key_id: person_id})
        link_id = link.id

    payload = TokenPayload(sub=user_id)
    async with Sess() as s:
        await _svc(s, ks, payload).open_session()
    async with Sess() as s:
        ep = await _svc(s, ks, payload).open_episode(
            EpisodeIn(category=ids['illness'], code='ep-1', name='ОРВИ'))
        eid = ep.id

    blob = b'%PDF-1.4 blood test\n' + b'q' * 400

    # --- загрузка документа на эпизод: блоб + Data + событие ---
    async with Sess() as s:
        data = await _svc(s, ks, payload).upload_document(
            blob, name='Анализ крови', code='cbc', category=ids['analysis'],
            media_type='application/pdf', episode_id=eid)
    assert data.hash and data.objectid == eid, data
    assert not hasattr(DataOut.model_validate(data), 'objectid')   # псевдоним/эпизод скрыт
    # блоб реально лёг в хранилище
    async with Sess() as s:
        stored = await FileStore(session=s).get(data.hash)
    assert stored == blob
    print('[ok] загрузка: блоб в FileStore + Data(метаданные) на эпизоде')

    # --- ИИ-конвейер: событие разобрано -> Property(source=ai) на эпизоде ---
    await drain(Sess)
    async with Sess() as s:
        ai = (await s.execute(select(t.Property).where(
            t.Property.table == 'entity', t.Property.objectid == eid,
            t.Property.code == 'summary'))).scalars().all()
    assert len(ai) == 1 and ai[0].value['source'] == 'ai', ai
    print('[ok] outbox data.extract разобран -> Property(source=ai) на эпизоде')

    # --- список документов эпизода ---
    async with Sess() as s:
        docs = await _svc(s, ks, payload).documents(episode_id=eid)
    assert len(docs) == 1 and docs[0].code == 'cbc'
    print('[ok] список документов эпизода')

    # --- загрузка на уровень пациента (без episode_id) ---
    async with Sess() as s:
        d2 = await _svc(s, ks, payload).upload_document(
            b'flu shot record', name='Прививка', code='vac', media_type='text/plain')
    assert d2.table == 'pseudonym' and d2.objectid == pseudonym_id
    print('[ok] загрузка на уровень пациента (псевдоним)')

    # --- ВОРОТА: загрузка на чужой эпизод -> 404 ---
    async with Sess() as s:
        foreign = t.Pseudonym(); s.add(foreign); await s.commit()
        fep = t.Entity(category=ids['illness'], code='ep-x', name='Чужой',
                       table='pseudonym', objectid=foreign.id)
        s.add(fep); await s.commit()
        foreign_eid = fep.id
    async with Sess() as s:
        with pytest.raises(HTTPException) as ei:
            await _svc(s, ks, payload).upload_document(
                b'x', name='x', code='x', episode_id=foreign_eid)
        assert ei.value.status_code == 404
    # чужой блоб не создан (загрузка отвалилась на воротах ДО put)
    async with Sess() as s:
        n = (await s.execute(select(func.count()).select_from(t.Blob))).scalar_one()
    assert n == 2, n                              # только два наших блоба
    print('[ok] ВОРОТА: загрузка на чужой эпизод -> 404, блоб не создан')

    # --- документы «на руки»: пациенту видны, в ИИ НЕ уходят ---
    async with Sess() as s:
        await _svc(s, ks, payload).upload_document(
            b'%PDF referral', name='Направление на УЗИ', code='referral',
            category=ids['referral'], media_type='application/pdf', episode_id=eid)
        await _svc(s, ks, payload).upload_document(
            b'%PDF prescription', name='Рецепт', code='prescription',
            category=ids['prescription'], media_type='application/pdf', episode_id=eid)
    async with Sess() as s:
        docs = await _svc(s, ks, payload).documents(episode_id=eid)
        ai_docs = await _episode_docs(s, eid)
    assert {d.code for d in docs} == {'cbc', 'referral', 'prescription'}, docs
    # в ИИ уходит только анализ: направление и рецепт — бумаги пациента,
    # не входные данные для оценки (утечка медданных в модель)
    assert len(ai_docs) == 1 and ai_docs[0][0] == blob, ai_docs
    print('[ok] направления и рецепты видны пациенту, но НЕ уходят в ИИ')

    # --- содержимое документа: своё отдаётся, чужое -> 404 ---
    async with Sess() as s:
        content, mime, dname = await _svc(s, ks, payload).document_content(data.id)
    assert content == blob and mime == 'application/pdf' and dname == 'Анализ крови'
    print('[ok] содержимое своего документа отдаётся (просмотр/печать)')

    # Data на чужом эпизоде со ССЫЛКОЙ НА СУЩЕСТВУЮЩИЙ блоб: 404 обязан прийти
    # от ворот (владение эпизодом), а не от «блоб не найден»
    async with Sess() as s:
        fdata = t.Data(category=ids['analysis'], code='cbc', name='Чужой анализ',
                       table='entity', objectid=foreign_eid,
                       hash=data.hash, algorithm=data.algorithm)
        s.add(fdata); await s.commit()
        fdata_id = fdata.id
    async with Sess() as s:
        with pytest.raises(HTTPException) as ei:
            await _svc(s, ks, payload).document_content(fdata_id)
        assert ei.value.status_code == 404
    print('[ok] ВОРОТА: документ чужого эпизода -> 404 (перебор id не отдаёт файл)')

    await eng.dispose()
    print('\nТЕСТ ЗАГРУЗКИ ДОКУМЕНТОВ ПРОЙДЕН')
