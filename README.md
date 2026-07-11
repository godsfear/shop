# shop

Backend-ядро для магазина / мед. клиники: категорийное ядро + EAV, темпоральная
модель с версиями, псевдонимизация (домены, мост с DEK, consent-first доступ),
transactional outbox, FSM, i18n.

## Запуск

Нужны живые Postgres (с PostGIS) и Redis — см. `Docker-Postgresql/`.

```
docker compose -f Docker-Postgresql/docker-compose.yml up -d
uv run alembic upgrade head        # схема
uv run python -m shop              # сервер (uvicorn с reload)
```

Роли БД (см. `src/shop/security.py`, применяются `apply_rls`): владелец `shop` —
только DDL/миграции (на проде DSN живёт на деплой-раннере); `app` — runtime-DSN
приложения (в проде `DATABASE_URI` указывает на `app`, пароль `APP_DB_PASSWORD`);
`research` — статистика под RLS по доменам.

## Прод

- Образ: `docker build -t shop .` — web-контейнер; воркеры (outbox, sweeper,
  пул псевдонимов) отдельным контейнером того же образа:
  `uv run python -m shop.worker`, web-реплики при этом с `RUN_WORKERS=false`.
- Соединения: `DATABASE_URI` через PgBouncer (порт 6432 в compose), пул
  session-режима — приложение остаётся на NullPool.
- Обязательные секреты окружения: `JWT_SECRET`, `KEK`, `APP_DB_PASSWORD`,
  `RESEARCH_PASSWORD`, `GOOGLE_API_KEY` (опционален — без него ИИ-заглушка).

## Тесты

```
uv run pytest
```

Тесты и `scripts/bootstrap_dev.py` пересоздают схему — остановите dev-сервер
(его outbox-воркер держит транзакции и блокирует `DROP SCHEMA`), а после
прогона верните сид: `uv run python scripts/bootstrap_dev.py`.
