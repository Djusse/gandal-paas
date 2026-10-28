#!/usr/bin/env bash
# Helper pour exécuter kubectl sur la VM via SSH
# Usage : ./ssh-kubectl.sh <commande kubectl>
set -euo pipefail

ELASTIC_IP="${ELASTIC_IP:-16.170.20.250}"
KEY_PATH="${KEY_PATH:-$HOME/gandal}"

# Toutes les commandes sont préfixées avec l'export KUBECONFIG
ssh -i "$KEY_PATH" ubuntu@"$ELASTIC_IP" "export KUBECONFIG=\$HOME/.kube/config && $*"
