import asyncio, base64, datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.cache import get_cache
from shop.models.user import UserCreate, Contact
from shop.services.user import UserService
from shop.services.auth import AuthService

URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'


async def test_main():
    await get_cache()._redis.flushdb()
    eng = create_async_engine(URI)
    async with eng.begin() as conn:
        await conn.execute(text('DROP SCHEMA public CASCADE'))
        await conn.execute(text('CREATE SCHEMA public'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
        await conn.run_sync(t.Root.metadata.create_all)
    Sess = async_sessionmaker(eng, expire_on_commit=False)

    # ключевая пара клиента
    private_key = Ed25519PrivateKey.generate()
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()

    async with Sess() as s:
        country = t.Country(iso2='ru', iso3='rus', name='Russia')
        s.add(country); await s.flush()
        place = t.Place(code='msk', name='Москва', country=country.id)
        s.add(place); await s.flush()
        person = t.Person(name={'last': 'Иванов'}, sex=True,
                          birthdate=datetime.date(1980, 5, 1), birth_place=place.id)
        s.add(person); await s.commit()
        svc = UserService(session=s)
        user = await svc.create(UserCreate(person=person.id,
                                           contact=Contact(email='key@x.com'),
                                           password='correct-horse',
                                           public_key=public_pem))
        nokey = await svc.create(UserCreate(person=person.id,
                                            contact=Contact(email='nokey@x.com'),
                                            password='correct-horse'))

    # --- успешный вход по ключу ---
    async with Sess() as s:
        svc = UserService(session=s)
        challenge = await svc.create_challenge('key@x.com')
        signature = private_key.sign(base64.b64decode(challenge.nonce))
        token = await svc.authenticate_by_key('key@x.com', base64.b64encode(signature).decode())
        payload = AuthService.verify_token(token.access_token)
        assert payload.sub == user.id
        print('[ok] challenge -> подпись -> JWT; sub совпадает')

        # --- одноразовость nonce ---
        try:
            await svc.authenticate_by_key('key@x.com', base64.b64encode(signature).decode())
            raise AssertionError('nonce переиспользован!')
        except HTTPException as e:
            assert e.status_code == 401
            print('[ok] повтор той же подписи: 401 (nonce одноразовый)')

        # --- неверная подпись (и nonce при этом сгорает) ---
        challenge = await svc.create_challenge('key@x.com')
        bad = Ed25519PrivateKey.generate().sign(base64.b64decode(challenge.nonce))
        try:
            await svc.authenticate_by_key('key@x.com', base64.b64encode(bad).decode())
            raise AssertionError('чужая подпись прошла!')
        except HTTPException as e:
            assert e.status_code == 401
            print('[ok] подпись чужим ключом: 401')
        good = private_key.sign(base64.b64decode(challenge.nonce))
        try:
            await svc.authenticate_by_key('key@x.com', base64.b64encode(good).decode())
            raise AssertionError('nonce пережил неудачную попытку!')
        except HTTPException as e:
            assert e.status_code == 401
            print('[ok] после неудачной попытки nonce сгорел (нет перебора подписей)')

        # --- без challenge / без ключа ---
        try:
            await svc.authenticate_by_key('key@x.com', base64.b64encode(good).decode())
            raise AssertionError('вход без challenge!')
        except HTTPException as e:
            assert e.status_code == 401
        try:
            await svc.create_challenge('nokey@x.com')
            raise AssertionError('challenge для учётки без ключа!')
        except HTTPException as e:
            assert e.status_code == 401
            print('[ok] без выданного challenge и для учётки без ключа: 401')

        # --- пароль продолжает работать (второй фактор/fallback) ---
        token = await svc.authenticate_user('key@x.com', 'correct-horse')
        assert AuthService.verify_token(token.access_token).sub == user.id
        print('[ok] парольный вход не сломан')

    await eng.dispose()
    print('\nТЕСТ CHALLENGE-RESPONSE ПРОЙДЕН')

