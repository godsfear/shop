"""Ключевой сервис (Postgres, KEK): политики break-glass, ACL, hash-chain аудит."""
import asyncio

import pytest
from sqlalchemy import select, text
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.keyservice import (AuditError, DbKeyService, KeyServiceError, PolicyError,
                             EMERGENCY, LEGAL, RECOVERY)

URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'


async def test_main():
    eng = create_async_engine(URI, poolclass=NullPool)
    async with eng.begin() as conn:
        await conn.execute(text('DROP SCHEMA public CASCADE'))
        await conn.execute(text('CREATE SCHEMA public'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
        await conn.run_sync(t.Root.metadata.create_all)
    Sess = async_sessionmaker(eng, expire_on_commit=False)
    ks = DbKeyService(Sess, approvals_required=2, veto_window_s=1)

    # ключи и DEK
    dek = ks.new_dek()
    await ks.create_key('escrow')
    await ks.create_key('group:doctors')
    with pytest.raises(KeyServiceError):
        await ks.create_key('escrow')                 # дубль
    escrow_copy = await ks.wrap('escrow', dek)
    group_copy = await ks.wrap('group:doctors', dek)

    # материал ключа в БД зашифрован KEK (не равен и не содержит Fernet-ключ открыто)
    async with Sess() as s:
        material = (await s.execute(select(t.Key.material).where(
            t.Key.id == 'escrow'))).scalar_one()
    assert material.startswith(b'gAAAA'), 'материал должен быть шифртекстом Fernet(KEK)'
    print('[ok] материал ключей в БД — шифртекст под KEK')

    # повседневный доступ группы по ACL
    await ks.grant('group:doctors', 'dr-ivanov')
    assert await ks.unwrap('group:doctors', group_copy, 'dr-ivanov') == dek
    with pytest.raises(PolicyError):
        await ks.unwrap('group:doctors', group_copy, 'dr-petrov')
    await ks.revoke('group:doctors', 'dr-ivanov')
    with pytest.raises(PolicyError):
        await ks.unwrap('group:doctors', group_copy, 'dr-ivanov')
    print('[ok] ACL: grant/unwrap/revoke')

    # emergency: правило двух
    rid = await ks.request_breakglass(EMERGENCY, 'escrow', 'nurse-1', 'пациент без сознания')
    with pytest.raises(PolicyError):
        await ks.execute(rid, escrow_copy)
    with pytest.raises(PolicyError):
        await ks.approve(rid, 'nurse-1')              # инициатор не подтверждает
    await ks.approve(rid, 'keyholder-1')
    with pytest.raises(PolicyError):
        await ks.execute(rid, escrow_copy)
    await ks.approve(rid, 'keyholder-2')
    assert await ks.execute(rid, escrow_copy) == dek
    with pytest.raises(PolicyError):
        await ks.execute(rid, escrow_copy)            # одноразовость
    print('[ok] emergency: правило двух + одноразовость')

    # legal: обязательные реквизиты
    with pytest.raises(PolicyError):
        await ks.request_breakglass(LEGAL, 'escrow', 'lawyer', 'ордер')
    rid = await ks.request_breakglass(LEGAL, 'escrow', 'lawyer', 'ордер',
                                      reference='дело 12-34/2026')
    await ks.approve(rid, 'keyholder-1')
    await ks.approve(rid, 'keyholder-2')
    assert await ks.execute(rid, escrow_copy) == dek
    print('[ok] legal: реквизиты обязательны')

    # recovery: окно вето
    rid = await ks.request_breakglass(RECOVERY, 'escrow', 'patient-x', 'утерян ключ')
    with pytest.raises(PolicyError):
        await ks.execute(rid, escrow_copy)            # окно не истекло
    with pytest.raises(PolicyError):
        await ks.approve(rid, 'keyholder-1')          # не подтверждается
    await ks.veto(rid, 'patient-x')
    with pytest.raises(PolicyError):
        await ks.execute(rid, escrow_copy)            # вето окончательно
    rid = await ks.request_breakglass(RECOVERY, 'escrow', 'patient-x', 'утерян ключ, повторно')
    await asyncio.sleep(1.2)
    assert await ks.execute(rid, escrow_copy) == dek
    print('[ok] recovery: окно вето и вето владельца')

    # аудит: целостность; «рестарт» = новый инстанс, состояние в БД общее
    n = await ks.verify_audit()
    assert n > 0
    ks2 = DbKeyService(Sess, approvals_required=2, veto_window_s=1)
    await ks2.create_key('group:billing')
    assert await ks2.verify_audit() == n + 1
    print('[ok] аудит: цепочка целостна, переживает «рестарт»')

    # подделка записи -> разрыв цепочки
    async with Sess() as s:
        row = (await s.execute(select(t.KeyAudit).order_by(t.KeyAudit.seq)
                               .offset(3).limit(1))).scalar_one()
        row.data = {**row.data, 'key_id': 'FAKE'}
        await s.commit()
    with pytest.raises(AuditError):
        await ks.verify_audit()
    print('[ok] подделка записи аудита обнаружена')

    await eng.dispose()
    print('\nТЕСТ КЛЮЧЕВОГО СЕРВИСА (PG + KEK) ПРОЙДЕН')
