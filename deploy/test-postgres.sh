#!/usr/bin/env bash
# test-postgres.sh — exécute la suite backend sur un PostgreSQL réel.
#
# Contrairement à SQLite en mémoire, PostgreSQL applique l'isolation des
# transactions : c'est le seul moyen de reproduire la course R1.
#
#   ./deploy/test-postgres.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
CONTAINER="${PG_CONTAINER:-gandal-pg-test}"
PORT="${PG_PORT:-55432}"
DB="gandal_test"
USER_NAME="paas"
PASSWORD="paas"

command -v docker >/dev/null 2>&1 || { echo "docker est requis" >&2; exit 1; }

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" \
  -e POSTGRES_USER="$USER_NAME" \
  -e POSTGRES_PASSWORD="$PASSWORD" \
  -e POSTGRES_DB="$DB" \
  -p "${PORT}:5432" \
  postgres:16-alpine >/dev/null

echo "==> Attente de PostgreSQL (max 60 s)"
for _ in $(seq 1 60); do
  if docker exec "$CONTAINER" pg_isready -U "$USER_NAME" -d "$DB" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! docker exec "$CONTAINER" pg_isready -U "$USER_NAME" -d "$DB" >/dev/null 2>&1; then
  echo "PostgreSQL n'a pas démarré" >&2
  docker logs "$CONTAINER" >&2 || true
  exit 1
fi

export PG_TEST_URL="postgresql+psycopg://${USER_NAME}:${PASSWORD}@localhost:${PORT}/${DB}"
echo "==> Suite unitaire (doit rester verte, SQLite en mémoire)"
(cd "$ROOT/backend" && python -m pytest -q)

echo "==> Suite d'intégration PostgreSQL (R1)"
(cd "$ROOT/backend" && python -m pytest -q tests_integration)

echo "==> Terminé"
