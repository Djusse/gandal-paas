#!/usr/bin/env bash
# verify-local.sh — vérifie la fusion sans cluster Kubernetes.
#
#   ./deploy/verify-local.sh              # tout
#   ./deploy/verify-local.sh --fast       # sans e2e ni PostgreSQL
#   PG_URL=postgresql+psycopg://... ./deploy/verify-local.sh   # PostgreSQL existant
#
# Ne modifie rien hors du dépôt : le venv est créé dans .venv/, la base e2e
# dans un fichier temporaire supprimé à la fin.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FAST=0
[ "${1:-}" = "--fast" ] && FAST=1

GREEN='\033[1;32m'; RED='\033[1;31m'; CYAN='\033[1;36m'; DIM='\033[2m'; NC='\033[0m'
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf "${GREEN}  [ OK ]${NC}  %s\n" "$1"; }
ko()   { FAIL=$((FAIL+1)); printf "${RED}  [ECHEC] %s${NC}\n" "$1"; }
step() { printf "\n${CYAN}==> %s${NC}\n" "$1"; }
note() { printf "${DIM}        %s${NC}\n" "$1"; }

run() {   # run "<libellé>" <commande...>
  local label="$1"; shift
  if "$@" >/tmp/gandal-verify.log 2>&1; then
    ok "$label"
  else
    ko "$label"
    printf "${DIM}"; tail -20 /tmp/gandal-verify.log; printf "${NC}"
  fi
}

# ------------------------------------------------------------- 0. venv
step "Environnement Python"
PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
  note "création de .venv (une seule fois)"
  python3 -m venv "$ROOT/.venv"
fi
"$PY" -m pip install -q --upgrade pip
if "$PY" -m pip install -q -r backend/requirements-dev.txt \
      -r orchestrator/requirements-dev.txt; then
  ok "dépendances installées"
else
  ko "installation des dépendances"
  exit 1
fi

# --------------------------------------------------------- 1. tests
step "Tests unitaires"
run "backend (37 tests)" bash -c "cd backend && '$PY' -m pytest -q"
run "orchestrateur (58 tests)" bash -c "cd orchestrator && '$PY' -m pytest -q"

# ---------------------------------------------------------- 2. ruff
step "Style et compilation"
RUFF="$ROOT/.venv/bin/ruff"
if [ -x "$RUFF" ]; then
  run "ruff backend" "$RUFF" check backend/app backend/tests
  run "ruff orchestrateur" "$RUFF" check orchestrator/gandal orchestrator/app orchestrator/tests orchestrator/gandal_deploy.py
elif command -v ruff >/dev/null 2>&1; then
  run "ruff backend" ruff check backend/app backend/tests
  run "ruff orchestrateur" ruff check orchestrator/gandal orchestrator/app orchestrator/tests orchestrator/gandal_deploy.py
else
  note "ruff absent, étape ignorée"
fi
run "compilation orchestrateur" bash -c "cd orchestrator && '$PY' -m compileall -q gandal app gandal_deploy.py"

# --------------------------------------------------- 3. docs et YAML
step "Documentation et manifestes"
run "liens Markdown" "$PY" - <<'PY'
import re, sys
from pathlib import Path

pattern = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
fence = re.compile(r"^\s*(```|~~~)")
plausible = re.compile(r"^[\w./%~-]+$")
errors = []

for md in Path(".").rglob("*.md"):
    if ".git" in md.parts or ".venv" in md.parts:
        continue
    in_code = False
    for lineno, line in enumerate(
        md.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
    ):
        if fence.match(line):
            in_code = not in_code
            continue
        if in_code:
            continue
        for target in pattern.findall(line):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            if not plausible.match(target):
                continue
            path = target.split("#", 1)[0]
            if path and not (md.parent / path).exists():
                errors.append(f"{md}:{lineno}: {target}")

if errors:
    print("\n".join(errors))
    sys.exit(1)
print("liens valides")
PY

run "manifestes YAML" "$PY" - <<'PY'
import glob, sys, yaml

paths = glob.glob("infra/k3s/*.yaml") + glob.glob("deploy/*.yml") + [
    ".github/workflows/ci.yml",
    ".pre-commit-config.yaml",
]
for path in paths:
    list(yaml.safe_load_all(open(path, encoding="utf-8")))
print(f"{len(paths)} manifestes valides")
PY

run "aucun ancien chemin" bash -c '
  set -e
  if [ -f gandal_deploy.py ] || [ -f install.sh ] || [ -f registry.yaml ]; then
    echo "fichier resté à la racine" >&2; exit 1
  fi
  # .github contient le motif de recherche lui-même : exclu.
  ! git grep -n -E "~/tests/validation\.sh|gandal-paas/gandal_deploy\.py" \
      -- ":!docs" ":!*.tex" ":!.github"
'

if [ "$FAST" = "1" ]; then
  step "Résumé"
  printf "  réussis : %d   échecs : %d\n" "$PASS" "$FAIL"
  [ "$FAIL" -eq 0 ] || exit 1
  exit 0
fi

# ------------------------------------------------------- 4. PostgreSQL
step "Isolation transactionnelle sur PostgreSQL (R1)"
PG_RUNNING=0
if [ -n "${PG_URL:-}" ]; then
  PG_TEST_URL="$PG_URL" run "tests d'intégration PostgreSQL" \
    bash -c "cd backend && '$PY' -m pytest -q tests_integration"
  PG_RUNNING=1
elif command -v docker >/dev/null 2>&1; then
  IMG="${PG_IMAGE:-postgres:16-alpine}"
  if docker image inspect "$IMG" >/dev/null 2>&1; then
    docker rm -f gandal-verify-pg >/dev/null 2>&1 || true
    docker run -d --name gandal-verify-pg \
      -e POSTGRES_USER=paas -e POSTGRES_PASSWORD=paas -e POSTGRES_DB=gandal_test \
      -p 55433:5432 "$IMG" >/dev/null
    # L'entrypoint redémarre le serveur après l'initialisation : `pg_isready`
    # répond une première fois puis le serveur s'arrête. On exige donc deux
    # requêtes authentifiées consécutives réussies.
    ready=0
    for _ in $(seq 1 120); do
      if docker exec gandal-verify-pg psql -U paas -d gandal_test -c 'SELECT 1' >/dev/null 2>&1; then
        ready=$((ready+1))
        [ "$ready" -ge 2 ] && break
      else
        ready=0
      fi
      sleep 1
    done
    PG_TEST_URL="postgresql+psycopg://paas:paas@127.0.0.1:55433/gandal_test" \
      run "tests d'intégration PostgreSQL" \
      bash -c "cd backend && '$PY' -m pytest -q tests_integration"
    docker rm -f gandal-verify-pg >/dev/null 2>&1 || true
    PG_RUNNING=1
  else
    note "image $IMG absente : test PostgreSQL ignoré (PG_IMAGE=... pour en choisir une)"
  fi
else
  note "docker absent : test PostgreSQL ignoré"
fi

# -------------------------------------------------------------- 5. e2e
step "Bout en bout en mode mock (sans cluster)"
DB_FILE="$ROOT/.verify-e2e.db"
rm -f "$DB_FILE"
PORT="${E2E_PORT:-8022}"
export DATABASE_URL="sqlite:///$DB_FILE"
export GITLAB_MODE=fake ORCHESTRATOR_MODE=mock AUTH_MODE=dev
export WEBHOOK_SECRET=dev-webhook-secret INTERNAL_TOKEN=dev-internal-token
export WEBHOOK_PUBLIC_URL="http://127.0.0.1:$PORT"
export RECOVERY_ENABLED=false

(
  cd backend
  "$PY" -m alembic upgrade head >/tmp/gandal-verify.log 2>&1
  exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
) >/tmp/gandal-verify-server.log 2>&1 &
SERVER_PID=$!
cleanup_e2e() { kill "$SERVER_PID" 2>/dev/null || true; wait "$SERVER_PID" 2>/dev/null || true; rm -f "$DB_FILE"; }
trap cleanup_e2e EXIT

for _ in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then break; fi
  sleep 0.5
done

if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
  ok "backend démarré sur :$PORT"
  if BACKEND_URL="http://127.0.0.1:$PORT" SKIP_HTTP=1 TIMEOUT=60 \
       WEBHOOK_SECRET=dev-webhook-secret bash deploy/e2e.sh; then
    ok "e2e mock : projet créé, déployé, supprimé"
  else
    ko "e2e mock"
  fi
else
  ko "backend non démarré (voir /tmp/gandal-verify-server.log)"
  tail -20 /tmp/gandal-verify-server.log || true
fi

cleanup_e2e
trap - EXIT

# ------------------------------------------------------------ résumé
step "Résumé"
printf "  réussis : %d   échecs : %d\n" "$PASS" "$FAIL"
[ "$PG_RUNNING" = "1" ] || note "PostgreSQL non exécuté : R1 n'est pas couvert ici"
echo
if [ "$FAIL" -eq 0 ]; then
  printf "${GREEN}Validation locale réussie.${NC}\n"
  printf "Reste à faire sur un cluster : orchestrator/validation.sh et e2e.sh avec ORCHESTRATOR_MODE=real.\n"
  exit 0
fi
printf "${RED}%d vérification(s) en échec.${NC}\n" "$FAIL"
exit 1
