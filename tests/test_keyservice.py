"""Заглушка ключевого сервиса: политики break-glass, ACL, hash-chain аудит."""
import json
import tempfile
import time

import pytest

from shop.keyservice import (AuditError, PolicyError, StubKeyService,
                             EMERGENCY, LEGAL, RECOVERY)


def test_keyservice():
    tmp = tempfile.mkdtemp()
    ks = StubKeyService(tmp, approvals_required=2, veto_window_s=1)

    def expect_deny(fn):
        with pytest.raises(PolicyError):
            fn()

    # ключи и DEK
    dek = ks.new_dek()
    ks.create_key('escrow')
    ks.create_key('group:doctors')
    escrow_copy = ks.wrap('escrow', dek)
    group_copy = ks.wrap('group:doctors', dek)

    # повседневный доступ группы по ACL
    ks.grant('group:doctors', 'dr-ivanov')
    assert ks.unwrap('group:doctors', group_copy, 'dr-ivanov') == dek
    expect_deny(lambda: ks.unwrap('group:doctors', group_copy, 'dr-petrov'))
    ks.revoke('group:doctors', 'dr-ivanov')
    expect_deny(lambda: ks.unwrap('group:doctors', group_copy, 'dr-ivanov'))

    # emergency: правило двух
    rid = ks.request_breakglass(EMERGENCY, 'escrow', 'nurse-1', 'пациент без сознания')
    expect_deny(lambda: ks.execute(rid, escrow_copy))
    expect_deny(lambda: ks.approve(rid, 'nurse-1'))  # инициатор не подтверждает
    ks.approve(rid, 'keyholder-1')
    expect_deny(lambda: ks.execute(rid, escrow_copy))
    ks.approve(rid, 'keyholder-2')
    assert ks.execute(rid, escrow_copy) == dek
    expect_deny(lambda: ks.execute(rid, escrow_copy))  # одноразовость

    # legal: обязательные реквизиты
    expect_deny(lambda: ks.request_breakglass(LEGAL, 'escrow', 'lawyer', 'ордер'))
    rid = ks.request_breakglass(LEGAL, 'escrow', 'lawyer', 'ордер', reference='дело 12-34/2026')
    ks.approve(rid, 'keyholder-1')
    ks.approve(rid, 'keyholder-2')
    assert ks.execute(rid, escrow_copy) == dek

    # recovery: окно вето
    rid = ks.request_breakglass(RECOVERY, 'escrow', 'patient-x', 'утерян ключ')
    expect_deny(lambda: ks.execute(rid, escrow_copy))   # окно не истекло
    expect_deny(lambda: ks.approve(rid, 'keyholder-1'))  # не подтверждается
    ks.veto(rid, 'patient-x')
    expect_deny(lambda: ks.execute(rid, escrow_copy))   # вето окончательно
    rid = ks.request_breakglass(RECOVERY, 'escrow', 'patient-x', 'утерян ключ, повторно')
    time.sleep(1.2)
    assert ks.execute(rid, escrow_copy) == dek

    # аудит: целостность, продолжение цепочки после рестарта, обнаружение подделки
    n = ks.verify_audit()
    assert n > 0
    ks2 = StubKeyService(tmp, approvals_required=2, veto_window_s=1)
    ks2.create_key('group:billing')
    assert ks2.verify_audit() == n + 1

    audit = ks.dir / 'audit.jsonl'
    lines = audit.read_text('utf-8').splitlines()
    entry = json.loads(lines[3])
    entry['data']['key_id'] = 'FAKE'
    lines[3] = json.dumps(entry, ensure_ascii=False)
    audit.write_text('\n'.join(lines) + '\n', 'utf-8')
    with pytest.raises(AuditError):
        ks.verify_audit()
