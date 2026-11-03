#!/usr/bin/env bash
# add-pc-key.sh <CLE_PUBLIQUE> — autorise une cle publique sur la VM.
#
#   ./add-pc-key.sh "ssh-ed25519 AAAAC3Nza... gandal-paas"
#
# A executer dans AWS CloudShell, qui possede deja la cle privee ~/gandal
# et dont l'IP figure dans le Security Group.
#
# Pourquoi : evite de transferer la cle PRIVEE depuis CloudShell vers le PC
# (copier-coller source d'erreurs "error in libcrypto").
set -euo pipefail

NAME="${NAME:-gandal-paas}"
STATE="$HOME/.${NAME}-state.sh"
KEY="${1:-}"

[ -n "$KEY" ] || { echo "usage: $0 \"ssh-ed25519 AAAA... commentaire\""; exit 1; }
case "$KEY" in
  ssh-ed25519\ *|ssh-rsa\ *) ;;
  *) echo "Cle invalide : elle doit commencer par 'ssh-ed25519 ' ou 'ssh-rsa '"; exit 1 ;;
esac

[ -f "$STATE" ] || { echo "Etat introuvable : $STATE"; exit 1; }
# shellcheck disable=SC1090
. "$STATE"

echo "==> Ajout de la cle sur ubuntu@${PUBLIC_IP}"
ssh -i "$HOME/gandal" \
    -o StrictHostKeyChecking=accept-new \
    -o ConnectTimeout=15 \
    "ubuntu@${PUBLIC_IP}" \
    "mkdir -p ~/.ssh && chmod 700 ~/.ssh && \
     touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && \
     grep -qF '$KEY' ~/.ssh/authorized_keys || echo '$KEY' >> ~/.ssh/authorized_keys; \
     echo '--- cles autorisees ---'; cut -d' ' -f1,3 ~/.ssh/authorized_keys"

echo
echo "Termine. Depuis votre PC :"
echo "  ssh -i ~/.ssh/gandal ubuntu@${PUBLIC_IP}"
