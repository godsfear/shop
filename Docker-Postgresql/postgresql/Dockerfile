FROM postgres:latest

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    postgresql-${PG_MAJOR}-postgis-3 \
    postgresql-${PG_MAJOR}-postgis-3-scripts \
    postgis \
    && rm -rf /var/lib/apt/lists/* \

COPY init.sql /docker-entrypoint-initdb.d/

RUN echo "host all  all    0.0.0.0/0  md5" >> /var/lib/postgresql/data/pg_hba.conf

CMD ["postgres"]

EXPOSE 5432