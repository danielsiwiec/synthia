FROM pgvector/pgvector:pg16 AS pgvector-builder

FROM postgres:16 AS postgres-base

COPY --from=pgvector-builder /usr/lib/postgresql/16/lib/vector.so /usr/lib/postgresql/16/lib/
COPY --from=pgvector-builder /usr/share/postgresql/16/extension/vector* /usr/share/postgresql/16/extension/

COPY init-db.sh /docker-entrypoint-initdb.d/

FROM postgres-base AS final

USER postgres

