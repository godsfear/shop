FROM postgres:16

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    postgresql-$PG_MAJOR-postgis-3 \
    postgresql-$PG_MAJOR-postgis-3-scripts \
    && rm -rf /var/lib/apt/lists/*

COPY init.sql /docker-entrypoint-initdb.d/
