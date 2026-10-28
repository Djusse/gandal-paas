#!/usr/bin/env bash
# Phase 7-8 : Exécuter les tests de validation
set -euo pipefail

ELASTIC_IP="${1:-16.170.20.250}"
KEY_PATH="${KEY_PATH:-$HOME/gandal}"

echo "==> Phase 7-8 : Exécution des tests de validation"

ssh -i "$KEY_PATH" ubuntu@"$ELASTIC_IP" bash << 'ENDSSH'
set -e
export KUBECONFIG=$HOME/.kube/config
export GANDAL_BASE_DOMAIN="${ELASTIC_IP}.sslip.io"

source ~/gandal-venv/bin/activate

echo "==> Lancement de tests/validation.sh"
~/tests/validation.sh alice memoire my-api

ENDSSH

echo ""
echo "==> Tests terminés !"
