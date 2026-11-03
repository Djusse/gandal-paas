#!/usr/bin/env bash
# e2e.sh — Test de bout en bout du PaaS.
#
#   ./deploy/e2e.sh                 # environnement déjà démarré
#   UP=1 ./deploy/e2e.sh            # démarre docker compose avant le test
#   RESILIENCE=1 ./deploy/e2e.sh    # redémarre l'orchestrateur pendant le déploiement
#   SKIP_HTTP=1 ./deploy/e2e.sh     # sans cluster (ORCHESTRATOR_MODE=mock)
#
# Vérifie : POST /projects -> image -> webhook success -> statut `deployed`
# -> HTTP 200 sur l'URL -> suppression.
#
# Prérequis :
#   - backend joignable (BACKEND_URL, défaut http://localhost:8000) ;
#   - ORCHESTRATOR_MODE=real pour que le déploiement soit réellement appliqué ;
#   - GITLAB_MODE=fake, qui produit une image du registry local.
#
# `SKIP_HTTP=1` n'exécute pas la vérification HTTP : en mode mock, l'URL
# (`{projet}.mock.gandal.local`) n'existe pas. Le test valide alors le câblage
# backend → orchestrateur → rappel → statut, et signale l'étape ignorée.
set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
OWNER="${OWNER:-e2e-user}"
PROJECT="${PROJECT:-e2e-app-$$}"
APP_PORT="${APP_PORT:-80}"
TIMEOUT="${TIMEOUT:-180}"
WEBHOOK_SECRET="${WEBHOOK_SECRET:-dev-webhook-secret}"
RESILIENCE="${RESILIENCE:-0}"
UP="${UP:-0}"
SKIP_HTTP="${SKIP_HTTP:-0}"
# Le tag de l'image produite est SHA[:8]. Le défaut correspond au tag publié
# par infra/k3s/install-gandal.sh dans le registry du cluster.
SHA="${SHA:-a1b2c3d4e5f6}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
ok()   { printf '\033[1;32m    OK : %s\033[0m\n' "$1"; }
fail() { printf '\033[1;31m    ECHEC : %s\033[0m\n' "$1" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || fail "$1 est requis"; }

need curl
need python3

json_field() {
  # json_field <clé> : lit un champ d'un JSON sur stdin (sans jq).
  python3 -c 'import json,sys; print(json.load(sys.stdin).get(sys.argv[1], ""))' "$1"
}

# ------------------------------------------------------------------ socle
if [ "$UP" = "1" ]; then
  say "Démarrage de l'environnement (docker compose)"
  ORCHESTRATOR_MODE=real RESILIENCE="$RESILIENCE" \
    docker compose -f "$COMPOSE_FILE" up -d --build
  for _ in $(seq 1 60); do
    if curl -fsS "$BACKEND_URL/health" >/dev/null 2>&1; then break; fi
    sleep 2
  done
fi

say "Backend : $BACKEND_URL"
HEALTH=$(curl -fsS "$BACKEND_URL/health" || true)
[ -n "$HEALTH" ] || fail "backend injoignable sur $BACKEND_URL"
ok "backend disponible"

# ------------------------------------------------------------ création
say "POST /projects ($PROJECT)"
CREATE=$(curl -fsS -X POST "$BACKEND_URL/projects" \
  -H 'Content-Type: application/json' \
  -H "X-Dev-User: $OWNER" \
  -d "{\"name\":\"$PROJECT\",\"app_port\":$APP_PORT}") \
  || fail "création du projet refusée"
PROJECT_ID=$(printf '%s' "$CREATE" | json_field id)
GITLAB_ID=$(printf '%s' "$CREATE" | json_field gitlab_project_id)
[ -n "$PROJECT_ID" ] || fail "réponse de création sans id"
ok "projet $PROJECT_ID (GitLab $GITLAB_ID), namespace proj-$PROJECT"

# --------------------------------------------------------------- webhook
say "Webhook pipeline success"
PIPELINE_ID=$(( (RANDOM * 32768 + RANDOM) % 900000 + 1000 ))

curl -fsS -X POST "$BACKEND_URL/webhooks/gitlab" \
  -H 'Content-Type: application/json' \
  -H "X-Gitlab-Token: $WEBHOOK_SECRET" \
  -d "{\"object_kind\":\"pipeline\",\"project\":{\"id\":$GITLAB_ID},\"object_attributes\":{\"id\":$PIPELINE_ID,\"status\":\"success\",\"sha\":\"$SHA\",\"ref\":\"main\"}}" \
  >/dev/null || fail "webhook refusé"
ok "pipeline $PIPELINE_ID enregistré (sha $SHA)"

# -------------------------------------------------------- résilience
if [ "$RESILIENCE" = "1" ]; then
  say "Résilience : redémarrage de l'orchestrateur pendant le déploiement"
  docker restart gandal-orchestrator >/dev/null 2>&1 \
    || printf '    (orchestrateur non conteneurisé, étape ignorée)\n'
  ok "orchestrateur redémarré"
fi

# -------------------------------------------------------------- attente
say "Attente du statut 'deployed' (max ${TIMEOUT}s)"
DEADLINE=$(( $(date +%s) + TIMEOUT ))
STATUS=""
URL=""
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  BODY=$(curl -fsS "$BACKEND_URL/projects/$PROJECT_ID/deployments" \
    -H "X-Dev-User: $OWNER" 2>/dev/null || echo '[]')
  LATEST=$(printf '%s' "$BODY" | python3 -c \
    'import json,sys; d=json.load(sys.stdin); print((d[0].get("status","pending") if d else "pending") + "|" + ((d[0].get("url") or "") if d else ""))')
  STATUS="${LATEST%%|*}"
  URL="${LATEST#*|}"
  case "$STATUS" in
    deployed|failed) break ;;
  esac
  sleep 5
done

[ "$STATUS" = "deployed" ] || fail "statut final : ${STATUS:-inconnu} (URL : ${URL:-aucune})"
ok "statut deployed, URL $URL"

# ---------------------------------------------------------------- HTTP
if [ "$SKIP_HTTP" = "1" ]; then
  say "Vérification HTTP ignorée (SKIP_HTTP=1, mode mock)"
  ok "URL rapportée : ${URL:-aucune}"
else
  say "Vérification HTTP de l'URL"
  CODE=$(curl -s -o /dev/null -m 15 -w '%{http_code}' "$URL" || true)
  if [ "$CODE" = "200" ]; then
    ok "HTTP 200 sur $URL"
  else
    fail "HTTP $CODE sur $URL (200 attendu) — utiliser SKIP_HTTP=1 en mode mock"
  fi
fi

# ---------------------------------------------------------- suppression
say "DELETE /projects/$PROJECT_ID"
curl -fsS -X DELETE "$BACKEND_URL/projects/$PROJECT_ID" \
  -H "X-Dev-User: $OWNER" >/dev/null || fail "suppression refusée"
ok "projet supprimé"

say "E2E réussi"
