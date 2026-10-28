#!/usr/bin/env bash
# provision-aws.sh — a executer dans AWS CloudShell.
#
#   ./provision-aws.sh up    <CHEMIN_CLE_PUBLIQUE> [IP_AUTORISEE]
#   ./provision-aws.sh down
#
# "up" cree : VPC 10.0.0.0/16, sous-reseau public, IGW, table de route,
# Security Group (22/6443 restreints, 80/443 ouverts), paire de cles importee,
# instance t3.large Ubuntu 24.04 avec 60 Go gp3, et Elastic IP associee.
# "down" supprime tout ce qui a ete cree.
#
# Prerequis : AWS CLI configuree (CloudShell l'a par defaut).
# La cle publique se cree sur VOTRE PC avec :
#   ssh-keygen -t ed25519 -f ~/.ssh/gandal -C gandal-paas
set -euo pipefail

NAME="${NAME:-gandal-paas}"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-eu-west-3}}"
STATE="$HOME/.${NAME}-state.sh"
ACTION="${1:-up}"

say()  { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
warn() { printf '\033[33m    %s\033[0m\n' "$1"; }

aws_() { aws --region "$REGION" "$@"; }

# --------------------------------------------------------------- nettoyage
if [ "$ACTION" = "down" ]; then
  [ -f "$STATE" ] || { echo "Etat introuvable : $STATE"; exit 1; }
  # shellcheck disable=SC1090
  . "$STATE"
  say "Suppression de $NAME (region $REGION)"
  aws_ ec2 terminate-instances --instance-ids "$INSTANCE_ID" >/dev/null 2>&1 || true
  aws_ ec2 wait instance-terminated --instance-ids "$INSTANCE_ID" 2>/dev/null || true
  [ -n "${ALLOC_ID:-}" ] && aws_ ec2 release-address --allocation-id "$ALLOC_ID" >/dev/null 2>&1 || true
  aws_ ec2 delete-security-group --group-id "$SG_ID" >/dev/null 2>&1 || true
  aws_ ec2 delete-key-pair --key-name "$NAME" >/dev/null 2>&1 || true
  aws_ ec2 detach-internet-gateway --internet-gateway-id "$IGW_ID" --vpc-id "$VPC_ID" >/dev/null 2>&1 || true
  aws_ ec2 delete-internet-gateway --internet-gateway-id "$IGW_ID" >/dev/null 2>&1 || true
  for rt in "${RT_ID:-}" ; do
    [ -n "$rt" ] && aws_ ec2 delete-route-table --route-table-id "$rt" >/dev/null 2>&1 || true
  done
  aws_ ec2 delete-subnet --subnet-id "$SUBNET_ID" >/dev/null 2>&1 || true
  aws_ ec2 delete-vpc --vpc-id "$VPC_ID" >/dev/null 2>&1 || true
  rm -f "$STATE"
  say "Supprime. Verifier la console (volumes EBS residuels possibles)."
  exit 0
fi

[ "$ACTION" = "up" ] || { echo "usage: $0 up <CLE_PUBLIQUE> [IP] | $0 down"; exit 1; }
PUBKEY="${2:?usage: $0 up <CHEMIN_CLE_PUBLIQUE.pub> [IP_AUTORISEE]}"
[ -f "$PUBKEY" ] || { echo "Cle publique introuvable : $PUBKEY"; exit 1; }

if [ -n "${3:-}" ]; then
  MYIP="$3"
else
  MYIP=$(curl -fsS https://checkip.amazonaws.com | tr -d '\n')
  warn "IP publique detectee automatiquement : $MYIP"
  warn "Si c'est l'IP de CloudShell et non la votre, relancez avec votre IP en 3e argument."
fi

say "Region : $REGION"
ACCOUNT=$(aws_ sts get-caller-identity --query Account --output text)
echo "    Compte : $ACCOUNT"

AZ=$(aws_ ec2 describe-availability-zones \
  --query 'AvailabilityZones[?State==`available`]|[0].ZoneName' --output text)
echo "    Zone   : $AZ"

# -------------------------------------------------------------------- VPC
say "VPC et reseau"
VPC_ID=$(aws_ ec2 create-vpc --cidr-block 10.0.0.0/16 \
  --tag-specifications "ResourceType=vpc,Tags=[{Key=Name,Value=$NAME}]" \
  --query 'Vpc.VpcId' --output text)
aws_ ec2 modify-vpc-attribute --vpc-id "$VPC_ID" --enable-dns-hostnames
echo "    VPC          : $VPC_ID"

SUBNET_ID=$(aws_ ec2 create-subnet --vpc-id "$VPC_ID" --cidr-block 10.0.0.0/24 \
  --availability-zone "$AZ" \
  --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=$NAME-public}]" \
  --query 'Subnet.SubnetId' --output text)
aws_ ec2 modify-subnet-attribute --subnet-id "$SUBNET_ID" --map-public-ip-on-launch
echo "    Sous-reseau  : $SUBNET_ID"

IGW_ID=$(aws_ ec2 create-internet-gateway \
  --tag-specifications "ResourceType=internet-gateway,Tags=[{Key=Name,Value=$NAME}]" \
  --query 'InternetGateway.InternetGatewayId' --output text)
aws_ ec2 attach-internet-gateway --internet-gateway-id "$IGW_ID" --vpc-id "$VPC_ID"

RT_ID=$(aws_ ec2 create-route-table --vpc-id "$VPC_ID" \
  --tag-specifications "ResourceType=route-table,Tags=[{Key=Name,Value=$NAME}]" \
  --query 'RouteTable.RouteTableId' --output text)
aws_ ec2 create-route --route-table-id "$RT_ID" \
  --destination-cidr-block 0.0.0.0/0 --gateway-id "$IGW_ID" >/dev/null
aws_ ec2 associate-route-table --route-table-id "$RT_ID" --subnet-id "$SUBNET_ID" >/dev/null
echo "    Passerelle   : $IGW_ID / route $RT_ID"

# ------------------------------------------------------------ Security Group
say "Security Group (22 et 6443 depuis $MYIP, 80 et 443 depuis partout)"
SG_ID=$(aws_ ec2 create-security-group --group-name "$NAME-sg" \
  --description "GANDAL PaaS simulation" --vpc-id "$VPC_ID" \
  --tag-specifications "ResourceType=security-group,Tags=[{Key=Name,Value=$NAME}]" \
  --query GroupId --output text)
aws_ ec2 authorize-security-group-ingress --group-id "$SG_ID" --ip-permissions \
  "IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges=[{CidrIp=$MYIP/32,Description=SSH}]" \
  "IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges=[{CidrIp=0.0.0.0/0,Description=HTTP-Traefik}]" \
  "IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=0.0.0.0/0,Description=HTTPS}]" \
  "IpProtocol=tcp,FromPort=6443,ToPort=6443,IpRanges=[{CidrIp=$MYIP/32,Description=API-Kubernetes}]" \
  >/dev/null
echo "    SG           : $SG_ID"

# ------------------------------------------------------------------ cle SSH
say "Import de la cle publique"
aws_ ec2 import-key-pair --key-name "$NAME" \
  --public-key-material "fileb://$PUBKEY" >/dev/null
echo "    KeyPair      : $NAME"

# --------------------------------------------------------------------- AMI
say "Recherche de l'AMI Ubuntu 24.04 LTS"
AMI_ID=""
for variant in ebs-gp3 ebs-gp2 ebs-gp3-arm64; do
  path="/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/${variant}/ami-id"
  candidate=$(aws_ ssm get-parameter --name "$path" \
    --query 'Parameter.Value' --output text 2>/dev/null || true)
  if [ -n "$candidate" ] && [ "$candidate" != "None" ]; then
    AMI_ID="$candidate"
    break
  fi
done
if [ -z "$AMI_ID" ]; then
  AMI_ID=$(aws_ ec2 describe-images --owners 099720109477 \
    --filters "Name=name,Values=ubuntu/images/hvm-ssd*/ubuntu-noble-24.04-amd64-server-*" \
              "Name=state,Values=available" \
    --query 'reverse(sort_by(Images,&CreationDate))[0].ImageId' --output text)
fi
echo "    AMI          : $AMI_ID"

# ---------------------------------------------------------------- instance
say "Creation de l'instance t3.large (60 Go gp3)"
INSTANCE_ID=$(aws_ ec2 run-instances \
  --image-id "$AMI_ID" \
  --instance-type t3.large \
  --key-name "$NAME" \
  --security-group-ids "$SG_ID" \
  --subnet-id "$SUBNET_ID" \
  --block-device-mappings \
    '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":60,"VolumeType":"gp3","DeleteOnTermination":true}}]' \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME}]" \
  --query 'Instances[0].InstanceId' --output text)
echo "    Instance     : $INSTANCE_ID"
aws_ ec2 wait instance-running --instance-ids "$INSTANCE_ID"

# -------------------------------------------------------------- Elastic IP
say "Elastic IP"
ALLOC_ID=$(aws_ ec2 allocate-address --domain vpc \
  --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=$NAME}]" \
  --query 'AllocationId' --output text)
aws_ ec2 associate-address --instance-id "$INSTANCE_ID" --allocation-id "$ALLOC_ID" >/dev/null
PUBLIC_IP=$(aws_ ec2 describe-addresses --allocation-ids "$ALLOC_ID" \
  --query 'Addresses[0].PublicIp' --output text)

# ------------------------------------------------------------------ etat
cat > "$STATE" <<EOF
NAME=$NAME
REGION=$REGION
VPC_ID=$VPC_ID
SUBNET_ID=$SUBNET_ID
IGW_ID=$IGW_ID
RT_ID=$RT_ID
SG_ID=$SG_ID
INSTANCE_ID=$INSTANCE_ID
ALLOC_ID=$ALLOC_ID
PUBLIC_IP=$PUBLIC_IP
EOF

say "Termine"
cat <<EOF

    Elastic IP   : $PUBLIC_IP
    Utilisateur  : ubuntu
    Cle privee   : celle creee sur votre PC (~/.ssh/gandal)

    Testez depuis votre PC :
      ssh -i ~/.ssh/gandal ubuntu@$PUBLIC_IP

    Etat enregistre dans : $STATE
    Suppression totale   : ./provision-aws.sh down

    RAPPEL COUT : l'Elastic IP et le volume gp3 sont factures meme
    instance arretee. Pensez a ./provision-aws.sh down apres la demo.

EOF
