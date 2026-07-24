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
- письма с кодами подтверждения — http://localhost:8025 (Mailpit);
- шина событий (RabbitMQ) — http://localhost:15672 (guest/guest).

Стек: `postgres` (PostGIS), `redis`, `rabbitmq`, `migrate` (одноразовый: схема +
RLS + сид), `api`, `worker`, `web` (nginx), `mailpit`. Данные БД — в томе `pgdata`.

Географический сид содержит связанные справочники `Country → Place`: страны,
столицы и города с населением от 100 тысяч, с русскими и английскими названиями.
Зафиксированный снимок получен из [Wikidata](https://www.wikidata.org/) (CC0);
обновление: `python scripts/fetch_geography.py`.

Шина событий (гибрид outbox + RabbitMQ, см. `eventbus.py`): atomicity «данные +
событие» держит outbox, relay перекачивает события в topic-exchange, консумеры
читают из очередей `shop.ai` (ИИ-разбор/оценка — масштабируется репликами
`worker`), `shop.mail`, `shop.notify` с дедупликацией (ProcessedEvent) и
ретраями через retry/dead-очереди. Переключатель `EVENT_BUS` (в compose у
`worker` = true); при `false` — воркер разбирает outbox напрямую (для тестов
и простого одноузлового деплоя). Перед продом задать `KEK`, `POSTGRES_PASSWORD`,
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
