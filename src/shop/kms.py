"""Google Cloud KMS: конверт над мастер-ключом (KEK).

Раньше KEK лежал в .env открытым. Теперь там KMS-шифротекст (KEK_ENCRYPTED):
на старте один раз просим KMS его расшифровать -> тот же KEK в память. Значение
KEK не меняется, поэтому все существующие DEK разворачиваются как прежде (см.
keyservice.py) — перешифровывать данные не нужно.

Что это даёт: мастер-ключа нет в открытом виде на диске/в бэкапе; доступ к нему
IAM-гейтится и логируется в KMS; ServiceAccount отзывается мгновенно. Чего НЕ
даёт: работающий сервер держит KEK в памяти и может расшифровать данные — это не
zero-knowledge (для него нужен клиентский owner-DEK).

Нет KEK_ENCRYPTED -> открытый settings.kek (dev/тесты, зависимость не грузится).
Аутентификация: GCP_SA_JSON (ключ SA одной строкой) либо, если пусто, ADC
(GOOGLE_APPLICATION_CREDENTIALS).

Выпуск KEK_ENCRYPTED из текущего KEK:  python -m shop.kms   (или --kek <value>)
"""
import base64
import json
from functools import lru_cache

from .settings import settings


def _client():
    from google.cloud import kms  # ленивый импорт: без KMS зависимость не нужна
    if settings.gcp_sa_json:
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_info(
            json.loads(settings.gcp_sa_json))
        return kms.KeyManagementServiceClient(credentials=creds)
    return kms.KeyManagementServiceClient()  # ADC (GOOGLE_APPLICATION_CREDENTIALS)


@lru_cache
def resolve_kek() -> str:
    """Плейнтекст KEK: из KMS (если задан KEK_ENCRYPTED) либо открытый settings.kek.
    Кэшируется — вызов KMS происходит один раз за процесс."""
    if not settings.kek_encrypted:
        return settings.kek
    if not settings.kms_key:
        raise RuntimeError('KEK_ENCRYPTED задан, но KMS_KEY пуст')
    resp = _client().decrypt(request={
        'name': settings.kms_key,
        'ciphertext': base64.b64decode(settings.kek_encrypted)})
    return resp.plaintext.decode()


def _wrap_cli() -> None:
    import sys
    plaintext = (sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == '--kek'
                 else settings.kek)
    if not settings.kms_key:
        sys.exit('KMS_KEY не задан в .env')
    resp = _client().encrypt(request={
        'name': settings.kms_key, 'plaintext': plaintext.encode()})
    print(base64.b64encode(resp.ciphertext).decode())


if __name__ == '__main__':
    _wrap_cli()
