#!/usr/bin/env bash
# open-sg.sh [IP] — autorise SSH (22) et l'API Kubernetes (6443) depuis une IP.
#
#   ./open-sg.sh                 # utilise l'IP publique vue par AWS
#   ./open-sg.sh 102.244.98.95   # IP explicite (celle de votre PC)
#
# A executer dans AWS CloudShell, apres provision-aws.sh up.
# Le script supprime toutes les anciennes regles SSH/6443 avant d'ajouter
# la nouvelle IP — evite l'accumulation de regles obsoletes a chaque session.
set -euo pipefail

NAME="${NAME:-gandal-paas}"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-eu-north-1}}"
STATE="$HOME/.${NAME}-state.sh"

[ -f "$STATE" ] || { echo "Etat introuvable : $STATE"; exit 1; }
# shellcheck disable=SC1090
. "$STATE"

IP="${1:-}"
if [ -z "$IP" ]; then
  IP=$(curl -fsS https://checkip.amazonaws.com | tr -d '\n')
  echo "IP detectee : $IP"
  echo "Si c'est l'IP de CloudShell et non votre PC, relancez :"
  echo "  ./open-sg.sh <IP_DE_VOTRE_PC>"
fi

echo "==> Suppression des anciennes regles SSH (22) et API Kubernetes (6443) sur ${SG_ID}"
for port in 22 6443; do
  # Recuperer toutes les CIDRs actuellement autorisees sur ce port
  OLD_CIDRS=$(aws ec2 describe-security-groups --region "$REGION" \
    --group-ids "$SG_ID" \
    --query "SecurityGroups[0].IpPermissions[?FromPort==\`${port}\`].IpRanges[].CidrIp" \
    --output text 2>/dev/null || true)

  for cidr in $OLD_CIDRS; do
    if aws ec2 revoke-security-group-ingress --region "$REGION" \
        --group-id "$SG_ID" \
        --protocol tcp --port "$port" --cidr "$cidr" \
        >/dev/null 2>&1; then
      echo "    port $port : ancienne regle $cidr supprimee"
    fi
  done
done

echo "==> Ajout de la nouvelle regle pour ${IP}/32 (ports 22 et 6443)"
for port in 22 6443; do
  label=$([ "$port" = 22 ] && echo SSH || echo API-Kubernetes)
  if aws ec2 authorize-security-group-ingress --region "$REGION" \
      --group-id "$SG_ID" \
      --ip-permissions "IpProtocol=tcp,FromPort=${port},ToPort=${port},IpRanges=[{CidrIp=${IP}/32,Description=${label}-${IP}}]" \
      >/dev/null 2>&1; then
    echo "    port $port : autorise pour ${IP}"
  else
    echo "    port $port : erreur (verifier la console AWS)"
  fi
done

echo
echo "Regles actuelles du groupe ${SG_ID} :"
aws ec2 describe-security-groups --region "$REGION" --group-ids "$SG_ID" \
  --query 'SecurityGroups[0].IpPermissions[].{Port:FromPort,CIDR:IpRanges[].CidrIp}' \
  --output table
