import asyncio, datetime

from jose import jwt as jose_jwt
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.models.person import PersonCreate
from shop.models.user import Contact, SignUp, UserCreate
from shop.cache import get_cache
from shop.services.user import UserService
from shop.services.auth import AuthService, get_current_user, require_roles
from shop.settings import settings

URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'


async def test_main():
    eng = create_async_engine(URI, poolclass=NullPool)
    async with eng.begin() as conn:
        await conn.execute(text('DROP SCHEMA public CASCADE'))
        await conn.execute(text('CREATE SCHEMA public'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
        await conn.run_sync(t.Root.metadata.create_all)
    Sess = async_sessionmaker(eng, expire_on_commit=False)

    # бутстрап identity-цепочки для пользователя
    async with Sess() as s:
        country = t.Country(iso2='ru', iso3='rus', name='Russia')
        s.add(country); await s.flush()
        place = t.Place(code='msk', name='Москва', country=country.id)
        s.add(place); await s.flush()
        person = t.Person(name={'last': 'Иванов'}, sex=True,
                          birthdate=datetime.date(1980, 5, 1), birth_place=place.id)
        s.add(person); await s.commit()
        person_id = person.id
        place_id = place.id

    # --- сквозная регистрация: персона встроена в signup ---
    async with Sess() as s:
        # хеш заранее — как в проде: пароль хешируется на шаге заявки (signup),
        # register_new_user вызывается после сверки кода
        token, new_user = await UserService(session=s).register_new_user(SignUp(
            person=PersonCreate(name={'last': 'Петров'}, sex=True,
                                birthdate=datetime.date(1990, 1, 1),
                                birth_place=place_id),
            contact=Contact(email=' Petrov@X.COM '),
            password='correct-horse'), AuthService.hash_password('correct-horse'),
            {'terms_version': 'v-test', 'terms_accepted_at': '2026-07-21T10:00:00+00:00'})
        signup_payload = AuthService.verify_token(token.access_token)
        new_user_id = new_user.id
    async with Sess() as s:
        me = await get_current_user(payload=signup_payload, session=s)
        assert me.contact.email == 'petrov@x.com'
    # согласие на обработку ПДн зафиксировано на учётке (юр. след)
    async with Sess() as s:
        row = await s.get(t.User, new_user_id)
        assert row.terms_version == 'v-test' and row.terms_accepted_at is not None
    print('[ok] согласие на обработку ПДн зафиксировано (версия + момент)')
    print('[ok] сквозная регистрация: Person создана внутри signup, токен валиден')

    # --- регистрация и содержимое токена ---
    async with Sess() as s:
        svc = UserService(session=s)
        user = await svc.create(UserCreate(
            person=person_id,
            contact=Contact(email=' Ivanov@Example.COM '),
            password='correct-horse'))
        token = AuthService.create_token(user)

    claims = jose_jwt.get_unverified_claims(token.access_token)
    assert set(claims) == {'iat', 'nbf', 'exp', 'sub', 'roles'}, claims
    assert 'contact' not in str(claims) and 'ivanov' not in str(claims).lower()
    print('[ok] в JWT только служебные claims + sub + roles; ПДн нет:', sorted(claims))

    payload = AuthService.verify_token(token.access_token)
    assert payload.sub == user.id and payload.roles == []
    print('[ok] verify_token -> TokenPayload(sub, roles)')

    # --- get_current_user грузит профиль из БД ---
    async with Sess() as s:
        me = await get_current_user(payload=payload, session=s)
        assert me.id == user.id and me.contact.email == 'ivanov@example.com'
    print('[ok] get_current_user: профиль из БД по sub')

    # --- роли: 403 без роли, выдача админом, доступ с ролью ---
    checker = require_roles(settings.admin_role)
    try:
        checker(payload)
        raise AssertionError('403 не сработал!')
    except HTTPException as e:
        assert e.status_code == 403
        print(f'[ok] без роли: 403 ({e.detail})')

    async with Sess() as s:
        svc = UserService(session=s)
        user = await svc.set_roles(user.id, ['admin', 'keyholder'])
        token2 = AuthService.create_token(user)
    payload2 = AuthService.verify_token(token2.access_token)
    assert checker(payload2).roles == ['admin', 'keyholder']
    print('[ok] роли выданы, require_roles пропускает; в новом токене:', payload2.roles)

    # --- аутентификация по контакту (JSONB) ---
    async with Sess() as s:
        svc = UserService(session=s)
        tok = await svc.authenticate_user(' IVANOV@EXAMPLE.COM ', 'correct-horse')
        assert AuthService.verify_token(tok.access_token).sub == user.id
        print('[ok] вход по email из JSONB-контакта')
        try:
            await svc.authenticate_user('IVANOV@EXAMPLE.COM', 'wrong-password')
            raise AssertionError('вход с неверным паролем!')
        except HTTPException as e:
            assert e.status_code == 401
            print('[ok] неверный пароль: 401')

    # --- восстановление пароля по коду (petrov, не тронут expire) ---
    await get_cache().set('pwreset:petrov@x.com', '654321', 60)
    async with Sess() as s:
        svc = UserService(session=s)
        try:                                  # неверный код -> 400, пароль тот же
            await svc.reset_password(' PETROV@X.COM ', '000000', 'BrandNew1')
            raise AssertionError('неверный код прошёл!')
        except HTTPException as e:
            assert e.status_code == 400
        await svc.reset_password(' PETROV@X.COM ', '654321', 'BrandNew1')  # верный
    async with Sess() as s:
        svc = UserService(session=s)
        tok = await svc.authenticate_user('PETROV@X.COM', 'BrandNew1')
        assert AuthService.verify_token(tok.access_token).sub == new_user_id
        try:                                  # старый пароль больше не работает
            await svc.authenticate_user('PETROV@X.COM', 'correct-horse')
            raise AssertionError('старый пароль ещё работает!')
        except HTTPException as e:
            assert e.status_code == 401
    async with Sess() as s:                   # код одноразовый: повтор -> 400
        try:
            await UserService(session=s).reset_password('petrov@x.com', '654321', 'Another1')
            raise AssertionError('код переиспользован!')
        except HTTPException as e:
            assert e.status_code == 400
    print('[ok] сброс пароля: неверный код 400, верный меняет пароль, старый не работает, код одноразовый')

    # --- деактивированный пользователь: токен жив, но 401 ---
    async with Sess() as s:
        svc = UserService(session=s)
        await svc.expire(user.id)
    async with Sess() as s:
        try:
            await get_current_user(payload=payload2, session=s)
            raise AssertionError('деактивированный прошёл!')
        except HTTPException as e:
            assert e.status_code == 401
            print('[ok] expire + живой токен = 401 (автофильтр ends)')

    await eng.dispose()
    print('\nТЕСТ АВТОРИЗАЦИИ ПРОЙДЕН')

