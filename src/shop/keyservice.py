"""Заглушка внешнего ключевого сервиса (HSM + policy-engine).

Контракт, который обязан выполнять боевой сервис (и эмулирует заглушка):

- ключи получателей (группы, escrow) НЕ покидают сервис — наружу только
  wrap/unwrap; у владельца-пациента свой ключ на клиенте, сервис его не видит;
- прямой unwrap разрешён только субъектам из ACL ключа (повседневная работа
  группы по гранту владельца); членство = ACL, ротация ключа не нужна;
- unwrap escrow-ключом — только через заявку break-glass по политике:
    emergency — N различных подтверждений (settings.breakglass_approvals,
                «правило двух»), подтверждающие несут одну выделенную роль
                (settings.breakglass_role — проверяется на слое API),
                инициатор подтверждать не может, исполнение немедленно;
    legal     — те же подтверждения + обязательные реквизиты основания;
    recovery  — без подтверждений, но исполнение только после окна вето
                (settings.veto_window_s), владелец может отменить заявку;
- каждое действие, включая отказы, пишется в append-only аудит
  с хеш-цепочкой ДО выполнения самого действия;
- уведомление владельца о каждой заявке — обязанность вызывающей стороны
  (очередь/Message), заглушка его не эмулирует.

ЗАГЛУШКА НЕБЕЗОПАСНА: ключи лежат открытым текстом в keys.json, заявки
живут в памяти процесса. Годится только для разработки и прогонов сценариев;
замена — реализация KeyService поверх Vault Transit / облачного KMS / HSM.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal, Protocol

from cryptography.fernet import Fernet

from .settings import settings

Kind = Literal['emergency', 'legal', 'recovery']

EMERGENCY: Kind = 'emergency'
LEGAL: Kind = 'legal'
RECOVERY: Kind = 'recovery'


class KeyServiceError(Exception):
    """Ошибка ключевого сервиса."""


class PolicyError(KeyServiceError):
    """Операция отклонена политикой."""


class AuditError(KeyServiceError):
    """Хеш-цепочка аудита нарушена."""


@dataclass
class BreakGlassRequest:
    id: str
    kind: Kind
    key_id: str
    requester: str
    reason: str
    reference: str | None
    created: datetime
    approvals: set[str] = field(default_factory=set)
    status: str = 'pending'  # pending | vetoed | executed


class KeyService(Protocol):
    """Интерфейс ключевого сервиса — точка замены заглушки на боевой бэкенд."""

    def create_key(self, key_id: str) -> None: ...
    def grant(self, key_id: str, actor: str) -> None: ...
    def revoke(self, key_id: str, actor: str) -> None: ...
    def wrap(self, key_id: str, plaintext: bytes) -> bytes: ...
    def unwrap(self, key_id: str, token: bytes, actor: str) -> bytes: ...
    def request_breakglass(self, kind: Kind, key_id: str, requester: str,
                           reason: str, reference: str | None = None) -> str: ...
    def approve(self, request_id: str, approver: str) -> None: ...
    def veto(self, request_id: str, by: str) -> None: ...
    def execute(self, request_id: str, token: bytes) -> bytes: ...
    def verify_audit(self) -> int: ...


class StubKeyService:
    def __init__(self, store_dir: str | Path,
                 approvals_required: int = 2,
                 veto_window_s: int = 7 * 24 * 3600):
        self.dir = Path(store_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._keys_path = self.dir / 'keys.json'
        self._audit_path = self.dir / 'audit.jsonl'
        self.approvals_required = approvals_required
        self.veto_window = timedelta(seconds=veto_window_s)
        self._requests: dict[str, BreakGlassRequest] = {}

        if self._keys_path.exists():
            data = json.loads(self._keys_path.read_text('utf-8'))
        else:
            data = {'keys': {}, 'acl': {}}
        self._keys: dict[str, str] = data['keys']
        self._acl: dict[str, list[str]] = data['acl']

        self._tip = '0' * 64
        if self._audit_path.exists():
            lines = self._audit_path.read_text('utf-8').splitlines()
            if lines:
                self._tip = json.loads(lines[-1])['hash']

    @staticmethod
    def new_dek() -> bytes:
        """Свежий ключ данных (DEK) для персоны/контура."""
        return os.urandom(32)

    # ------------------------------------------------------------------ #
    #  Ключи и повседневный доступ по ACL
    # ------------------------------------------------------------------ #
    def create_key(self, key_id: str) -> None:
        if key_id in self._keys:
            raise KeyServiceError(f"ключ '{key_id}' уже существует")
        self._audit('key.create', key_id=key_id)
        self._keys[key_id] = Fernet.generate_key().decode()
        self._acl.setdefault(key_id, [])
        self._save()

    def grant(self, key_id: str, actor: str) -> None:
        self._require_key(key_id)
        self._audit('key.grant', key_id=key_id, actor=actor)
        if actor not in self._acl[key_id]:
            self._acl[key_id].append(actor)
            self._save()

    def revoke(self, key_id: str, actor: str) -> None:
        self._require_key(key_id)
        self._audit('key.revoke', key_id=key_id, actor=actor)
        if actor in self._acl[key_id]:
            self._acl[key_id].remove(actor)
            self._save()

    def wrap(self, key_id: str, plaintext: bytes) -> bytes:
        self._require_key(key_id)
        self._audit('key.wrap', key_id=key_id)
        return Fernet(self._keys[key_id].encode()).encrypt(plaintext)

    def unwrap(self, key_id: str, token: bytes, actor: str) -> bytes:
        self._require_key(key_id)
        if actor not in self._acl.get(key_id, ()):
            self._audit('key.unwrap.denied', key_id=key_id, actor=actor)
            raise PolicyError(f"'{actor}' не имеет прямого доступа к ключу '{key_id}'")
        self._audit('key.unwrap', key_id=key_id, actor=actor)
        return Fernet(self._keys[key_id].encode()).decrypt(token)

    # ------------------------------------------------------------------ #
    #  Break-glass
    # ------------------------------------------------------------------ #
    def request_breakglass(self, kind: Kind, key_id: str, requester: str,
                           reason: str, reference: str | None = None) -> str:
        self._require_key(key_id)
        if kind not in (EMERGENCY, LEGAL, RECOVERY):
            raise KeyServiceError(f"неизвестный вид заявки '{kind}'")
        if kind == LEGAL and not reference:
            self._audit('breakglass.request.denied', kind=kind, key_id=key_id,
                        requester=requester, why='нет реквизитов основания')
            raise PolicyError('для legal-заявки обязательны реквизиты основания (reference)')
        req = BreakGlassRequest(
            id=str(uuid.uuid4()), kind=kind, key_id=key_id, requester=requester,
            reason=reason, reference=reference, created=datetime.now(timezone.utc),
        )
        self._requests[req.id] = req
        self._audit('breakglass.request', request_id=req.id, kind=kind, key_id=key_id,
                    requester=requester, reason=reason, reference=reference)
        return req.id

    def approve(self, request_id: str, approver: str) -> None:
        req = self._get(request_id)
        if req.kind == RECOVERY:
            self._audit('breakglass.approve.denied', request_id=request_id,
                        approver=approver, why='recovery исполняется после окна вето')
            raise PolicyError('recovery-заявка не подтверждается — она исполняется после окна вето')
        if approver == req.requester:
            self._audit('breakglass.approve.denied', request_id=request_id,
                        approver=approver, why='инициатор не может подтверждать')
            raise PolicyError('инициатор заявки не может её подтверждать')
        req.approvals.add(approver)
        self._audit('breakglass.approve', request_id=request_id,
                    approver=approver, total=len(req.approvals))

    def veto(self, request_id: str, by: str) -> None:
        req = self._get(request_id)
        if req.status != 'pending':
            raise PolicyError(f"заявка в статусе '{req.status}', вето невозможно")
        self._audit('breakglass.veto', request_id=request_id, by=by)
        req.status = 'vetoed'

    def execute(self, request_id: str, token: bytes) -> bytes:
        req = self._get(request_id)
        if req.status != 'pending':
            self._audit('breakglass.execute.denied', request_id=request_id,
                        why=f'статус {req.status}')
            raise PolicyError(f"заявка в статусе '{req.status}'")
        if req.kind in (EMERGENCY, LEGAL):
            if len(req.approvals) < self.approvals_required:
                self._audit('breakglass.execute.denied', request_id=request_id,
                            why=f'подтверждений {len(req.approvals)}/{self.approvals_required}')
                raise PolicyError(
                    f'нужно {self.approvals_required} подтверждений, есть {len(req.approvals)}')
        else:  # RECOVERY
            deadline = req.created + self.veto_window
            if datetime.now(timezone.utc) < deadline:
                self._audit('breakglass.execute.denied', request_id=request_id,
                            why='окно вето не истекло')
                raise PolicyError(f'окно вето открыто до {deadline.isoformat()}')
        self._audit('breakglass.execute', request_id=request_id,
                    kind=req.kind, key_id=req.key_id)
        req.status = 'executed'  # одноразовость: одна заявка — один unwrap
        return Fernet(self._keys[req.key_id].encode()).decrypt(token)

    # ------------------------------------------------------------------ #
    #  Аудит: append-only с хеш-цепочкой
    # ------------------------------------------------------------------ #
    def verify_audit(self) -> int:
        """Проверяет цепочку, возвращает число записей; AuditError при разрыве."""
        prev = '0' * 64
        count = 0
        if not self._audit_path.exists():
            return 0
        for line in self._audit_path.read_text('utf-8').splitlines():
            entry = json.loads(line)
            if entry['prev'] != prev or entry['hash'] != self._entry_hash(entry):
                raise AuditError(f'цепочка аудита нарушена на записи {count}')
            prev = entry['hash']
            count += 1
        return count

    def _audit(self, event: str, **data) -> None:
        entry = {
            'ts': datetime.now(timezone.utc).isoformat(),
            'event': event,
            'data': data,
            'prev': self._tip,
        }
        entry['hash'] = self._entry_hash(entry)
        with self._audit_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        self._tip = entry['hash']

    @staticmethod
    def _entry_hash(entry: dict) -> str:
        payload = json.dumps(
            {k: entry[k] for k in ('ts', 'event', 'data', 'prev')},
            sort_keys=True, ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    # ------------------------------------------------------------------ #
    #  Внутреннее
    # ------------------------------------------------------------------ #
    def _save(self) -> None:
        self._keys_path.write_text(
            json.dumps({'keys': self._keys, 'acl': self._acl}, indent=1), 'utf-8')

    def _require_key(self, key_id: str) -> None:
        if key_id not in self._keys:
            raise KeyServiceError(f"ключ '{key_id}' не существует")

    def _get(self, request_id: str) -> BreakGlassRequest:
        req = self._requests.get(request_id)
        if req is None:
            raise KeyServiceError(f"заявка '{request_id}' не найдена")
        return req


@lru_cache
def get_key_service() -> StubKeyService:
    """Точка получения сервиса; при замене на боевой бэкенд меняется только она."""
    return StubKeyService(
        store_dir=settings.keyservice_dir,
        approvals_required=settings.breakglass_approvals,
        veto_window_s=settings.veto_window_s,
    )
