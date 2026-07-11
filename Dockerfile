# Прод-образ бэкенда. Web: `docker run <img>` (RUN_WORKERS=false при >1 реплике);
# фоновые воркеры отдельным контейнером: `docker run <img> uv run python -m shop.worker`.
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# зависимости отдельным слоем — кэш переживает правки кода
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
RUN uv sync --frozen --no-dev && \
    useradd --system --no-create-home shop && chown -R shop /app
USER shop

EXPOSE 8000
# без reload; секреты (JWT_SECRET, KEK, DATABASE_URI под ролью app) — из окружения
CMD ["uv", "run", "--no-dev", "uvicorn", "shop.app:app", "--host", "0.0.0.0", "--port", "8000"]
