#!/usr/bin/env bash
# install-gandal.sh <IP_PUBLIQUE> — installe la plateforme fusionnée sur K3s.
#
# À exécuter SUR LA VM, après infra/k3s/install.sh (Docker, K3s, registry).
# Le dépôt doit être présent sur la VM (git clone ou scp).
#
#   ./infra/k3s/install-gandal.sh 16.170.20.250
#
# Étapes :
#   1. secrets aléatoires (orchestrateur, interne, webhook, base) ;
#   2. build et push des images dans le registry du nœud ;
#   3. PostgreSQL, orchestrateur (RBAC), backend ;
#   4. domaine sslip.io injecté dans les Ingress ;
#   5. vérifications de santé.
set -euo pipefail

PUBLIC_IP="${1:?usage: $0 <IP_PUBLIQUE>}"
DOMAIN="${GANDAL_BASE_DOMAIN:-${PUBLIC_IP}.sslip.io}"
REGISTRY="${GANDAL_REGISTRY:-localhost:5000}"
NS="gandal-system"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

say()  { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
ok()   { printf '\033[1;32m    OK : %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m    !! %s\033[0m\n' "$1"; }

need() { command -v "$1" >/dev/null 2>&1 || { echo "$1 est requis" >&2; exit 1; }; }
need openssl
need python3

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
command -v kubectl >/dev/null 2>&1 || { echo "kubectl absent" >&2; exit 1; }
kubectl get nodes >/dev/null 2>&1 || { echo "cluster injoignable" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "docker absent" >&2; exit 1; }
DOCKER="docker"
docker info >/dev/null 2>&1 || DOCKER="sudo docker"

rand() { openssl rand -hex "${1:-24}"; }

# ------------------------------------------------------------ 1. secrets
say "Secrets (générés une seule fois)"
cd "$REPO_ROOT"
mkdir -p .secrets
SECRETS_FILE="$REPO_ROOT/.secrets/cluster.env"
if [ -f "$SECRETS_FILE" ]; then
  # shellcheck disable=SC1090
  . "$SECRETS_FILE"
  ok "secrets existants réutilisés ($SECRETS_FILE)"
else
  ORCHESTRATOR_TOKEN="$(rand 24)"
  INTERNAL_TOKEN="$(rand 24)"
  WEBHOOK_SECRET="$(rand 24)"
  POSTGRES_PASSWORD="$(rand 16)"
  cat > "$SECRETS_FILE" <<EOF
ORCHESTRATOR_TOKEN=$ORCHESTRATOR_TOKEN
INTERNAL_TOKEN=$INTERNAL_TOKEN
WEBHOOK_SECRET=$WEBHOOK_SECRET
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
EOF
  chmod 600 "$SECRETS_FILE"
  ok "secrets créés ($SECRETS_FILE, ignoré par git)"
fi

kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f - >/dev/null

kubectl -n "$NS" create secret generic backend-secrets \
  --from-literal=WEBHOOK_SECRET="$WEBHOOK_SECRET" \
  --from-literal=INTERNAL_TOKEN="$INTERNAL_TOKEN" \
  --from-literal=ORCHESTRATOR_TOKEN="$ORCHESTRATOR_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

kubectl -n "$NS" create secret generic backend-db-secret \
  --from-literal=POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  --from-literal=DATABASE_URL="postgresql+psycopg://paas:${POSTGRES_PASSWORD}@backend-db:5432/paas" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

kubectl -n "$NS" create secret generic orchestrator-config \
  --from-literal=ORCHESTRATOR_TOKEN="$ORCHESTRATOR_TOKEN" \
  --from-literal=INTERNAL_TOKEN="$INTERNAL_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null
ok "secrets appliqués dans $NS"

# ------------------------------------------------------------- 2. images
say "Images (build + push vers $REGISTRY)"
$DOCKER build -q -t "$REGISTRY/gandal/backend:latest" "$REPO_ROOT/backend" >/dev/null
$DOCKER push -q "$REGISTRY/gandal/backend:latest" >/dev/null
ok "backend"

$DOCKER build -q -t "$REGISTRY/gandal/orchestrator:latest" "$REPO_ROOT/orchestrator" >/dev/null
$DOCKER push -q "$REGISTRY/gandal/orchestrator:latest" >/dev/null
ok "orchestrateur"

# Image applicative utilisée par les déploiements de démonstration.
# Elle est publiée sous le tag du pipeline simulé : les 8 premiers caractères
# du SHA d'exemple `a1b2c3d4e5f6...` (voir deploy/e2e.sh, qui utilise le même
# SHA par défaut).
DEMO_TAG="${GANDAL_DEMO_TAG:-a1b2c3d4}"
$DOCKER build -q -t "$REGISTRY/paas/demo:$DEMO_TAG" "$REPO_ROOT/demo" >/dev/null
$DOCKER push -q "$REGISTRY/paas/demo:$DEMO_TAG" >/dev/null
ok "démo (paas/demo:$DEMO_TAG)"

# Sonde du test d'isolation (curl) : construite depuis l'image nginx si elle
# est disponible localement ou téléchargeable.
if ! $DOCKER image inspect "$REGISTRY/curl:latest" >/dev/null 2>&1; then
  if $DOCKER pull -q curlimages/curl:latest >/dev/null 2>&1; then
    $DOCKER tag curlimages/curl:latest "$REGISTRY/curl:latest"
    $DOCKER push -q "$REGISTRY/curl:latest" >/dev/null
    ok "sonde curl"
  else
    warn "image curl indisponible : le test 3 de validation.sh échouera"
  fi
fi

# -------------------------------------------------------- 3. PostgreSQL
say "PostgreSQL"
kubectl apply -f "$REPO_ROOT/infra/k3s/postgres.yaml" >/dev/null
kubectl -n "$NS" rollout status deploy/backend-db --timeout=180s
ok "base prête"

# ----------------------------------------------------- 4. orchestrateur
say "Orchestrateur (ServiceAccount + RBAC)"
# Le manifeste contient un Secret de démonstration : on retire ce bloc pour
# ne pas écraser celui créé ci-dessus avec des jetons faibles.
python3 - "$REPO_ROOT/infra/k3s/orchestrator.yaml" <<'PY' > /tmp/orchestrator-clean.yaml
import sys

try:
    import yaml
except ImportError:
    # Pas de PyYAML sur la VM : on découpe le document sur les séparateurs
    # et on retire uniquement le bloc Secret `orchestrator-config`.
    blocks = open(sys.argv[1], encoding="utf-8").read().split("\n---\n")
    kept = [
        block for block in blocks
        if not ("kind: Secret" in block and "name: orchestrator-config" in block)
    ]
    sys.stdout.write("\n---\n".join(kept))
else:
    docs = [d for d in yaml.safe_load_all(open(sys.argv[1], encoding="utf-8")) if d]
    kept = [
        d for d in docs
        if not (
            d.get("kind") == "Secret"
            and d.get("metadata", {}).get("name") == "orchestrator-config"
        )
    ]
    yaml.safe_dump_all(kept, sys.stdout, sort_keys=False, allow_unicode=True)
PY
kubectl apply -f /tmp/orchestrator-clean.yaml >/dev/null
kubectl -n "$NS" set env deploy/orchestrator \
  GANDAL_BASE_DOMAIN="$DOMAIN" >/dev/null
kubectl -n "$NS" rollout status deploy/orchestrator --timeout=180s
ok "orchestrateur prêt (domaine $DOMAIN)"

# ----------------------------------------------------------- 5. backend
say "Backend"
kubectl apply -f "$REPO_ROOT/infra/k3s/backend.yaml" >/dev/null
kubectl -n "$NS" rollout status deploy/backend --timeout=240s
ok "backend prêt"

# ---------------------------------------------------------- 6. Ingress
say "Ingress (API sur api.$DOMAIN)"
sed "s|PLACEHOLDER_DOMAIN|$DOMAIN|" \
  "$REPO_ROOT/infra/k3s/backend-ingress.yaml" \
  | kubectl apply -f - >/dev/null
ok "Ingress configuré"

# ------------------------------------------------------- 7. vérifications
say "Vérifications"
for _ in $(seq 1 30); do
  if curl -fsS "http://api.${DOMAIN}/health" >/dev/null 2>&1; then break; fi
  sleep 4
done

if curl -fsS "http://api.${DOMAIN}/health" >/dev/null 2>&1; then
  ok "backend joignable : http://api.${DOMAIN}/health"
else
  warn "backend non joignable depuis cet hôte (DNS sslip.io ou Traefik)"
  kubectl -n "$NS" get pods
fi

if kubectl -n "$NS" exec deploy/orchestrator -- \
     curl -fsS http://localhost:8100/health >/dev/null 2>&1; then
  ok "orchestrateur : /health dans le cluster"
else
  warn "orchestrateur : /health indisponible"
fi

cat <<EOF

Installation terminée.

  API           : http://api.${DOMAIN}
  Orchestrateur : http://orchestrator.${NS}.svc.cluster.local:8100
  Secrets       : ${SECRETS_FILE}

Tester de bout en bout depuis la VM :

  BACKEND_URL=http://api.${DOMAIN} \\
  WEBHOOK_SECRET=${WEBHOOK_SECRET} \\
  ORCHESTRATOR_MODE=real \\
  ./deploy/e2e.sh

  ./orchestrator/validation.sh alice memoire my-api

Arrêter l'infrastructure facturable :

  infra/aws/provision-aws.sh down

EOF
