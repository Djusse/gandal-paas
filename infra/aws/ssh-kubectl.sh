#!/usr/bin/env bash
# Helper pour exécuter kubectl sur la VM via SSH
# Usage : ELASTIC_IP=1.2.3.4 ./ssh-kubectl.sh <commande kubectl>
set -euo pipefail

ELASTIC_IP="${ELASTIC_IP:?definir ELASTIC_IP (adresse publique de la VM)}"
KEY_PATH="${KEY_PATH:-$HOME/gandal}"

# Toutes les commandes sont préfixées avec l'export KUBECONFIG
ssh -i "$KEY_PATH" "ubuntu@${ELASTIC_IP}" "export KUBECONFIG=\$HOME/.kube/config && $*"
