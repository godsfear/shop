# shop

Персональный учёт здоровья: категорийное ядро + EAV, темпоральная модель с
версиями, псевдонимизация (домены, мост с DEK, consent-first доступ), ключи в
Postgres под KEK, transactional outbox, FSM, интервью-анамнез, ИИ-разбор
документов и оценка эпизода (Gemini), React-фронт.

## Всё одной командой (Docker)

```
cp .env.example .env        # впишите JWT_SECRET (openssl rand -base64 48)
docker compose up --build
```

- приложение — http://localhost:8080 (nginx раздаёт SPA и проксирует `/api`);
- письма с кодами подтверждения — http://localhost:8025 (Mailpit).

Стек: `postgres` (PostGIS), `redis`, `migrate` (одноразовый: схема + RLS + сид),
`api`, `worker` (outbox/sweeper/пул псевдонимов), `web` (nginx), `mailpit`.
Данные БД — в томе `pgdata`. Перед продом задать `KEK`, `POSTGRES_PASSWORD`,
`APP_DB_PASSWORD`, `RESEARCH_PASSWORD`; `GOOGLE_API_KEY` опционален (без него —
детерминированная ИИ-заглушка).

Почта: локально письма ловит Mailpit. Для реальной доставки замените SMTP у
сервисов `api`/`worker` на релей (SES/SendGrid/свой сервер) — самостоятельная
доставка в чужие ящики требует настройки DNS домена (SPF/DKIM/DMARC/PTR).

## Локальная разработка (без контейнеров приложения)

Только инфраструктура в Docker, api/фронт — на хосте:

```
docker compose -f Docker-Postgresql/docker-compose.yml up -d
uv run python scripts/bootstrap_dev.py    # схема + RLS + сид (пересоздаёт!)
uv run uvicorn shop.app:app --port 8000   # бэкенд
npm --prefix web run dev                  # фронт на :5173 (проксирует /api)
```

Роли БД (см. `src/shop/security.py`, `apply_rls`): владелец `shop` — только
DDL/миграции; `app` — runtime-DSN приложения; `research` — статистика под RLS.

## Тесты

```
uv run pytest
```

Тесты и `scripts/bootstrap_dev.py` пересоздают схему — остановите dev-сервер
(его outbox-воркер держит транзакции и блокирует `DROP SCHEMA`), а после
прогона верните сид: `uv run python scripts/bootstrap_dev.py`.
