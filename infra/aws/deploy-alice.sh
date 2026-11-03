#!/usr/bin/env bash
# Phase 4-6 : Déployer l'application de test (Alice)
#
#   ./deploy-alice.sh <IP_PUBLIQUE>
#
# L'IP et la clé peuvent aussi venir de l'environnement (ELASTIC_IP, KEY_PATH).
set -euo pipefail

ELASTIC_IP="${1:-${ELASTIC_IP:-}}"
KEY_PATH="${KEY_PATH:-$HOME/gandal}"

if [ -z "$ELASTIC_IP" ]; then
  echo "ERREUR : IP publique manquante." >&2
  echo "Usage : $0 <IP_PUBLIQUE>" >&2
  exit 1
fi

echo "==> Phase 4-6 : Déploiement de l'application Alice"

ssh -i "$KEY_PATH" "ubuntu@${ELASTIC_IP}" bash <<ENDSSH
set -e
export KUBECONFIG=\$HOME/.kube/config
export GANDAL_BASE_DOMAIN="${ELASTIC_IP}.sslip.io"

source ~/gandal-venv/bin/activate

echo "==> Variables d'environnement :"
echo "    GANDAL_BASE_DOMAIN=\$GANDAL_BASE_DOMAIN"
echo "    KUBECONFIG=\$KUBECONFIG"

echo ""
echo "==> Déploiement d'Alice/memoire/my-api"
python3 "\$HOME/gandal-paas/orchestrator/gandal_deploy.py" deploy \
  alice memoire my-api localhost:5000/my-api:v1 80

echo ""
echo "==> État du déploiement"
kubectl get pods -n proj-memoire

echo ""
echo "==> Attente que les pods soient Ready (max 60s)"
kubectl wait --for=condition=Ready pods -l gandal.io/app=my-api -n proj-memoire --timeout=60s || true

echo ""
echo "==> URL d'accès"
python3 "\$HOME/gandal-paas/orchestrator/gandal_deploy.py" status alice memoire my-api

ENDSSH

echo ""
echo "==> Déploiement terminé"
echo "    Testez : curl http://memoire.${ELASTIC_IP}.sslip.io"
