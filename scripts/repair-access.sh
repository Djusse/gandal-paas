#!/usr/bin/env bash
# repair-access.sh "<CLE_PUBLIQUE_PC>" — retablit l'acces SSH a la VM.
#
#   ./repair-access.sh "ssh-ed25519 AAAAC3... gandal-paas"
#
# A executer dans AWS CloudShell.
#
# Contexte : si authorized_keys a ete vide ou corrompu, la cle de CloudShell
# ne fonctionne plus. EC2 Instance Connect permet de pousser une cle publique
# temporaire via l'API AWS, sans redemarrer l'instance. On s'en sert pour
# reecrire authorized_keys proprement avec la cle du PC ET celle de CloudShell.
#
# Prerequis : paquet ec2-instance-connect present sur la VM (inclus dans les
# AMI Ubuntu officielles) et droit ec2-instance-connect:SendSSHPublicKey.
set -euo pipefail

NAME="${NAME:-gandal-paas}"
STATE="$HOME/.${NAME}-state.sh"
PC_KEY="${1:-}"

[ -f "$STATE" ] || { echo "Etat introuvable : $STATE"; exit 1; }
# shellcheck disable=SC1090
. "$STATE"

REGION="${REGION:-eu-north-1}"
AZ=$(aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].Placement.AvailabilityZone' --output text)

CLOUD_KEY=$(ssh-keygen -y -f "$HOME/gandal")

echo "==> Instance $INSTANCE_ID ($AZ)"

# 1. Pousser une cle temporaire (valable 60 s) via l'API
echo "==> Envoi de la cle temporaire par EC2 Instance Connect"
aws ec2-instance-connect send-ssh-public-key \
  --region "$REGION" \
  --instance-id "$INSTANCE_ID" \
  --availability-zone "$AZ" \
  --instance-os-user ubuntu \
  --ssh-public-key "$CLOUD_KEY" >/dev/null
echo "    OK (valable 60 s)"

# 2. Reecrire authorized_keys des que possible
REMOTE="mkdir -p \$HOME/.ssh && chmod 700 \$HOME/.ssh && : > \$HOME/.ssh/authorized_keys"
printf -v REMOTE '%s && printf "%%s\\n" "%s" >> $HOME/.ssh/authorized_keys' "$REMOTE" "$CLOUD_KEY"
if [ -n "$PC_KEY" ]; then
  case "$PC_KEY" in
    ssh-ed25519\ *|ssh-rsa\ *) ;;
    *) echo "Cle PC invalide, elle doit commencer par 'ssh-ed25519 '"; exit 1 ;;
  esac
  printf -v REMOTE '%s && printf "%%s\\n" "%s" >> $HOME/.ssh/authorized_keys' "$REMOTE" "$PC_KEY"
fi
REMOTE="$REMOTE && chmod 600 \$HOME/.ssh/authorized_keys && echo '--- cles en place ---' && cat \$HOME/.ssh/authorized_keys"

for attempt in 1 2 3; do
  if ssh -i "$HOME/gandal" -o StrictHostKeyChecking=accept-new \
         -o ConnectTimeout=10 "ubuntu@${PUBLIC_IP}" "$REMOTE" 2>/dev/null; then
    break
  fi
  echo "    tentative $attempt echouee, nouvelle cle temporaire..."
  aws ec2-instance-connect send-ssh-public-key --region "$REGION" \
    --instance-id "$INSTANCE_ID" --availability-zone "$AZ" \
    --instance-os-user ubuntu --ssh-public-key "$CLOUD_KEY" >/dev/null
  sleep 3
done

echo
echo "==> Verification finale"
ssh -i "$HOME/gandal" -o ConnectTimeout=10 "ubuntu@${PUBLIC_IP}" \
  'echo connexion OK; hostname; whoami'
