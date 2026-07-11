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

## Тесты

```
uv run pytest
```
