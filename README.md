# memory-knowledge

## Docker mode switching

Use the repo `Makefile` instead of manually renaming override files:

- `make local`
  - copies `docker-compose.override.yml.local` to `docker-compose.override.yml`
  - intended for local Postgres/Qdrant/Neo4j development
- `make remote`
  - removes `docker-compose.override.yml`
  - intended when the server should target remote databases only
- `make mode-status`
  - prints whether the local override is currently active

Typical startup:

- local stack: `COMPOSE_PROFILES=local docker compose up -d`
- remote-targeted server only: `docker compose up -d server`

## Supported PostgreSQL bootstrap path

For the current schema line, the supported database bootstrap path is:

- `alembic upgrade head`

In local Docker mode, PostgreSQL now starts as an empty database container and the
server applies migrations on startup through `docker/entrypoint.sh`.

`docker/init-pg.sql` is retained only as a deprecated historical snapshot. It is
not part of the supported current bootstrap flow.

## Remote PostgreSQL note

For new Supabase projects, the direct host `db.<project-ref>.supabase.co` may lag DNS propagation. When that happens:

- use the pooler endpoint `aws-0-<region>.pooler.supabase.com:6543`
- disable prepared statement caching if needed with `statement_cache_size=0`

Once direct DNS is available, the direct connection can be used again if that performs better for your workload.
