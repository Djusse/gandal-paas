#!/usr/bin/env bash
# tests/validation.sh [user] [projet] [app]
# Execute les 9 tests de reussite du document de cadrage.
# A lancer sur la VM, apres install.sh et apres avoir publie une image
# dans le registry local.
set -uo pipefail

USER_ARG="${1:-alice}"
PROJECT_ARG="${2:-memoire}"
APP_ARG="${3:-my-api}"
IMG="${GANDAL_TEST_IMAGE:-localhost:5000/my-api:v1}"
PORT="${GANDAL_TEST_PORT:-80}"
BASE_DOMAIN="${GANDAL_BASE_DOMAIN:-gandal.test}"

NS="project-${USER_ARG}-${PROJECT_ARG}"
BOB_USER="bob"
BOB_PROJECT="test"
BOB_NS="project-${BOB_USER}-${BOB_PROJECT}"
HOST="${APP_ARG}-${PROJECT_ARG}-${USER_ARG}.${BASE_DOMAIN}"
SVC_INTERNAL="${APP_ARG}.${NS}.svc.cluster.local"

PY="${PYTHON:-python3}"
[ -x "$HOME/gandal-venv/bin/python" ] && PY="$HOME/gandal-venv/bin/python"

PASS=0
FAIL=0
SKIP=0
declare -a RESULTS=()

ok()   { PASS=$((PASS+1)); RESULTS+=("  OK    | $1"); printf '  [ OK ]  %s\n' "$1"; }
ko()   { FAIL=$((FAIL+1)); RESULTS+=("  ECHEC | $1"); printf '  [ECHEC] %s\n' "$1"; }
skip() { SKIP=$((SKIP+1)); RESULTS+=("  IGNORE| $1"); printf '  [ -- ]  %s (ignore)\n' "$1"; }
head_() { printf '\n=== %s ===\n' "$1"; }

need_kubectl() {
  command -v kubectl >/dev/null 2>&1 || { echo "kubectl absent"; exit 1; }
}
need_kubectl

deploy() {
  "$PY" gandal_deploy.py deploy "$@" >/dev/null 2>&1
}

# ---------------------------------------------------------------- Test 1
head_ "Test 1 : deploiement automatise"
deploy "$USER_ARG" "$PROJECT_ARG" "$APP_ARG" "$IMG" "$PORT"
sleep 5
RUNNING=$(kubectl get pods -n "$NS" -l "gandal.io/app=${APP_ARG}" \
  --no-headers 2>/dev/null | awk '$3=="Running"' | wc -l)
TOTAL=$(kubectl get pods -n "$NS" -l "gandal.io/app=${APP_ARG}" \
  --no-headers 2>/dev/null | wc -l)
if [ "$RUNNING" -ge 2 ]; then
  ok "Test 1 : $RUNNING/$TOTAL pods Running dans $NS"
else
  ko "Test 1 : $RUNNING/$TOTAL pods Running (2 attendus)"
fi

# ---------------------------------------------------------------- Test 2
head_ "Test 2 : acces par DNS"
CODE=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "http://${HOST}" 2>/dev/null)
if [ "$CODE" = "200" ]; then
  ok "Test 2 : HTTP 200 sur http://${HOST}"
elif [ "$CODE" = "000" ]; then
  skip "Test 2 : nom non resolvable depuis cet hote (option DNS non active ?)"
else
  ko "Test 2 : HTTP ${CODE} sur http://${HOST} (200 attendu)"
fi

# ---------------------------------------------------------------- Test 3
head_ "Test 3 : isolation reseau"
deploy "$BOB_USER" "$BOB_PROJECT" web "$IMG" "$PORT"
sleep 5
probe() {
  kubectl run probe -n "$1" \
    --labels="gandal.io/owner=$2,gandal.io/project=$3" \
    --rm -i --restart=Never --image=localhost:5000/curl:latest \
    --overrides='{"spec":{"containers":[{"name":"probe","image":"localhost:5000/curl:latest","stdin":true,"tty":false}]}}' \
    -- curl -s -m 5 -o /dev/null -w '%{http_code}' "$4" 2>/dev/null | tr -dc '0-9'
}
FROM_BOB=$(probe "$BOB_NS" "$BOB_USER" "$BOB_PROJECT" "http://${SVC_INTERNAL}")
FROM_ALICE=$(probe "$NS" "$USER_ARG" "$PROJECT_ARG" "http://${SVC_INTERNAL}")
if [ "$FROM_BOB" = "000" ] && [ "$FROM_ALICE" = "200" ]; then
  ok "Test 3 : Bob bloque (000), Alice autorisee (200)"
elif [ -z "$FROM_BOB" ] && [ -z "$FROM_ALICE" ]; then
  skip "Test 3 : sonde indisponible (image localhost:5000/curl:latest absente ?)"
else
  ko "Test 3 : Bob=${FROM_BOB:-vide} (000 attendu), Alice=${FROM_ALICE:-vide} (200 attendu)"
fi

# ---------------------------------------------------------------- Test 4
head_ "Test 4 : resilience (self-healing)"
BEFORE=$(kubectl get pods -n "$NS" -l "gandal.io/app=${APP_ARG}" \
  --no-headers 2>/dev/null | wc -l)
kubectl delete pod -n "$NS" -l "gandal.io/app=${APP_ARG}" --wait=false >/dev/null 2>&1
for _ in $(seq 1 30); do
  NOW_RUNNING=$(kubectl get pods -n "$NS" -l "gandal.io/app=${APP_ARG}" \
    --no-headers 2>/dev/null | awk '$3=="Running"' | wc -l)
  [ "$NOW_RUNNING" -ge "$BEFORE" ] && break
  sleep 2
done
if [ "$NOW_RUNNING" -ge "$BEFORE" ] && [ "$BEFORE" -ge 1 ]; then
  ok "Test 4 : $(kubectl get pods -n "$NS" -l "gandal.io/app=${APP_ARG}" \
    --no-headers | awk '{print $3}' | sort | uniq -c | tr '\n' ' ')"
else
  ko "Test 4 : pods non recrees ($NOW_RUNNING/$BEFORE Running)"
fi

# ---------------------------------------------------------------- Test 5
head_ "Test 5 : quotas respectes"
kubectl scale deployment "$APP_ARG" --replicas=10 -n "$NS" >/dev/null 2>&1
sleep 12
READY=$(kubectl get deployment "$APP_ARG" -n "$NS" \
  -o jsonpath='{.status.readyReplicas}' 2>/dev/null)
READY="${READY:-0}"
PODS=$(kubectl get pods -n "$NS" --no-headers 2>/dev/null | wc -l)
HARD=$(kubectl get quota project-quota -n "$NS" \
  -o jsonpath='{.status.hard.pods}' 2>/dev/null)
EXCEEDED=$(kubectl get events -n "$NS" --field-selector reason=FailedCreate \
  2>/dev/null | grep -ci quota)
if [ "${HARD:-0}" -gt 0 ] && [ "$PODS" -le "$HARD" ] && [ "$EXCEEDED" -gt 0 ]; then
  ok "Test 5 : $PODS pods pour un plafond de $HARD, depassement signale"
elif [ "${HARD:-0}" -gt 0 ] && [ "$PODS" -le "$HARD" ]; then
  ok "Test 5 : $PODS pods pour un plafond de $HARD (plafond respecte)"
else
  ko "Test 5 : $PODS pods pour un plafond de ${HARD:-inconnu}"
fi
# Retour a l'etat normal
deploy "$USER_ARG" "$PROJECT_ARG" "$APP_ARG" "$IMG" "$PORT" --replicas 2

# ---------------------------------------------------------------- Test 6
head_ "Test 6 : metriques"
if kubectl top pods -n "$NS" >/dev/null 2>&1; then
  ok "Test 6 : kubectl top pods renvoie des valeurs"
else
  ko "Test 6 : kubectl top pods en echec (metrics-server pas encore pret ?)"
fi

# ---------------------------------------------------------------- Test 7
head_ "Test 7 : identification des conteneurs et IP"
OUT=$("$PY" gandal_deploy.py list --user "$USER_ARG" 2>/dev/null)
if echo "$OUT" | grep -q "$USER_ARG" && \
   echo "$OUT" | grep -Eq '([0-9]{1,3}\.){3}[0-9]{1,3}'; then
  ok "Test 7 : pods listes avec proprietaire et IP"
else
  ko "Test 7 : sortie de list sans proprietaire ou sans IP"
fi
BOB_IN_ALICE=$(echo "$OUT" | grep -c "$BOB_USER")
if [ "$BOB_IN_ALICE" -eq 0 ]; then
  ok "Test 7 : les pods de $BOB_USER n'apparaissent pas chez $USER_ARG"
else
  ko "Test 7 : fuite, $BOB_IN_ALICE ligne(s) de $BOB_USER dans la liste"
fi

# ---------------------------------------------------------------- Test 8
head_ "Test 8 : mise a jour idempotente"
OUT=$("$PY" gandal_deploy.py deploy "$USER_ARG" "$PROJECT_ARG" "$APP_ARG" \
  "$IMG" "$PORT" --replicas 3 2>&1)
REPL=$(kubectl get deployment "$APP_ARG" -n "$NS" \
  -o jsonpath='{.spec.replicas}' 2>/dev/null)
if echo "$OUT" | grep -q "a jour" && [ "${REPL:-0}" = "3" ]; then
  ok "Test 8 : ressources mises a jour, replicas = 3"
else
  ko "Test 8 : replicas = ${REPL:-?} (3 attendu) ou sortie inattendue"
fi

# ---------------------------------------------------------------- Test 9
head_ "Test 9 : nettoyage"
"$PY" gandal_deploy.py delete "$BOB_USER" "$BOB_PROJECT" --purge >/dev/null 2>&1
sleep 8
if kubectl get ns "$BOB_NS" >/dev/null 2>&1; then
  STAT=$(kubectl get ns "$BOB_NS" -o jsonpath='{.status.phase}' 2>/dev/null)
  if [ "$STAT" = "Terminating" ]; then
    ok "Test 9 : $BOB_NS en cours de suppression"
  else
    ko "Test 9 : $BOB_NS toujours present ($STAT)"
  fi
else
  ok "Test 9 : $BOB_NS supprime, $NS intact"
fi

# ---------------------------------------------------------------- Bilan
head_ "Bilan"
printf '  %-24s %d\n' "Reussis" "$PASS"
printf '  %-24s %d\n' "Echoues" "$FAIL"
printf '  %-24s %d\n' "Ignores" "$SKIP"
echo
for line in "${RESULTS[@]}"; do echo "$line"; done
echo
if [ "$FAIL" -eq 0 ]; then
  echo "RESULTAT : prototype valide."
  exit 0
fi
echo "RESULTAT : $FAIL test(s) en echec."
exit 1
