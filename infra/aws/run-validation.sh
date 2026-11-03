#!/usr/bin/env bash
# Phase 7-8 : Exécuter les tests de validation sur la VM.
#
#   ./run-validation.sh [IP_PUBLIQUE] [user] [projet] [app]
#
# ELASTIC_IP peut aussi être fourni par l'environnement. Le domaine de base
# est dérivé de l'IP (sslip.io) sauf si GANDAL_BASE_DOMAIN est déjà défini.
set -euo pipefail

ELASTIC_IP="${1:-${ELASTIC_IP:-}}"
USER_ARG="${2:-alice}"
PROJECT_ARG="${3:-memoire}"
APP_ARG="${4:-my-api}"
KEY_PATH="${KEY_PATH:-$HOME/gandal}"

if [ -z "$ELASTIC_IP" ]; then
  echo "ERREUR : IP publique manquante." >&2
  echo "Usage : $0 <IP_PUBLIQUE> [user] [projet] [app]" >&2
  exit 1
fi

# Le heredoc n'est PAS entre quotes : les variables locales sont expansées ici,
# celles qui doivent l'être sur la VM sont échappées (\$HOME, \$KUBECONFIG).
ssh -i "$KEY_PATH" "ubuntu@${ELASTIC_IP}" bash <<ENDSSH
set -e
export KUBECONFIG=\$HOME/.kube/config
export GANDAL_BASE_DOMAIN="${ELASTIC_IP}.sslip.io"

source ~/gandal-venv/bin/activate

echo "==> Lancement de orchestrator/validation.sh"
\$HOME/gandal-paas/orchestrator/validation.sh "${USER_ARG}" "${PROJECT_ARG}" "${APP_ARG}"
ENDSSH

echo ""
echo "==> Tests terminés"
