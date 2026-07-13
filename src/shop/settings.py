from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # .env ищется в корне репозитория независимо от рабочей директории запуска
    model_config = SettingsConfigDict(case_sensitive=False,
                                      env_file=str(Path(__file__).resolve().parents[2] / ".env"),
                                      env_file_encoding="utf-8",
                                      extra="ignore")
    server_host: str = '127.0.0.1'
    server_port: int = 8000
    database_uri: str = 'sqlite+aiosqlite:///./database.sqlite3'
    jwt_algorithm: str = 'HS256'
    # без дефолта: пустой ключ подписи означал бы токены без защиты
    jwt_secret: str
    jwt_expires_s: int = 3600
    challenge_ttl_s: int = 60              # жизнь nonce challenge-входа (в Redis)
    # echo логирует SQL с параметрами (ПДн!) — только для локальной отладки;
    # в файл параметры не попадают в любом случае (см. logger.py)
    sql_echo: bool = False
    api_prefix: str = '/api/v1'
    admin_role: str = 'admin'              # роль управления учётными записями/ролями
    # ключевой сервис (ключи в PG под KEK, см. keyservice.py)
    kek: str = 'dev-kek'                   # мастер-ключ шифрования ключей; в проде ОБЯЗАТЕЛЬНО в .env
    breakglass_approvals: int = 2          # «правило двух»
    breakglass_role: str = 'keyholder'     # единственная роль подтверждающих
    veto_window_s: int = 7 * 24 * 3600     # окно вето recovery-заявки
    pseudonym_pool_batch: int = 100        # размер партии пополнения пула псевдонимов
    pseudonym_pool_target: int = 100       # целевой размер пула (фоновый добор)
    pseudonym_pool_check_s: float = 300.0  # период фоновой проверки/добора пула
    research_password: str = 'research'    # dev-заглушка; в проде задать в .env
    app_db_password: str = 'app'           # runtime-роль приложения; в проде задать в .env
    # ИИ-разбор документов (services/extract.py); нет ключа -> детерминированная заглушка
    google_api_key: str | None = None      # Gemini; задаётся в .env, в код не пишется
    gemini_model: str = 'gemini-2.5-flash'
    # Redis-кэш (см. cache.py); недоступность Redis не роняет приложение
    redis_uri: str = 'redis://localhost:6379/0'
    cache_ttl_user_s: int = 300            # профиль пользователя
    cache_ttl_ref_s: int = 3600            # справочники (версионируемое пространство)
    cache_ttl_bridge_s: int = 300          # сессия разрешённого моста
    medsession_ttl_s: int = 3600           # сессия доступа к медданным (псевдоним в Redis)
    # transactional outbox (см. outbox.py)
    outbox_poll_s: float = 1.0             # пауза воркера при пустой очереди
    outbox_max_attempts: int = 5           # попыток до пометки события мёртвым
    outbox_backoff_s: float = 5.0          # задержка ретрая × номер попытки (тесты ставят 0)
    consent_sweep_s: float = 3600.0        # период фонового протухания согласий (until)
    # фоновые воркеры в web-процессе; false на репликах многопроцессного прода
    # (тогда воркеры — одним процессом: python -m shop.worker)
    run_workers: bool = True
    # почта: подтверждение регистрации; без SMTP код пишется в лог (dev)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_starttls: bool = True              # false для локальной ловушки (Mailpit)
    smtp_user: str = ''
    smtp_password: str = ''
    mail_from: str = 'noreply@localhost'
    confirm_ttl_s: int = 24 * 3600         # жизнь кода подтверждения (Redis)
    # периметр HTTP
    auth_rate_limit: int = 10              # попыток /auth/* с одного IP за окно
    auth_rate_window_s: int = 60           # окно rate limit (сек)
    cors_origins: list[str] = []           # CORS_ORIGINS='["https://app.example.com"]'


settings = Settings()
