#!/usr/bin/env bash
# deploy-demo.sh — Préparation et séquence complète de la démonstration live.
# A exécuter sur la VM : ssh -i ~/gandal ubuntu@16.170.20.250
# Usage : ./scripts/deploy-demo.sh [prepare|run|clean]
set -euo pipefail

ELASTIC_IP="${ELASTIC_IP:-16.170.20.250}"
export KUBECONFIG="$HOME/.kube/config"
export GANDAL_BASE_DOMAIN="${ELASTIC_IP}.sslip.io"

PY="$HOME/gandal-venv/bin/python"
DEPLOY="$PY $HOME/gandal-paas/gandal_deploy.py"
URL="http://landing-demo-alice.${GANDAL_BASE_DOMAIN}"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
ok()   { printf '\033[1;32m    OK : %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m    !! %s\033[0m\n' "$1"; }

# ------------------------------------------------------------------ prepare
prepare() {
  say "Etape 1 — Purge des namespaces de demo existants"
  for ns in "alice demo" "alice memoire" "bob test"; do
    user=$(echo "$ns" | cut -d' ' -f1)
    proj=$(echo "$ns" | cut -d' ' -f2)
    $DEPLOY delete "$user" "$proj" --purge 2>/dev/null && ok "project-${user}-${proj} supprime" || true
  done
  kubectl get ns | grep -E 'project-' || ok "Aucun namespace applicatif restant"

  say "Etape 2 — Verification du socle"
  kubectl get nodes
  kubectl -n gandal-system get deploy private-registry | grep '1/1' \
    && ok "Registry operationnel" || { warn "Registry non pret"; exit 1; }

  say "Etape 3 — Construction et push des images"
  DEMO_DIR="$(dirname "$0")/../demo"
  cd "$DEMO_DIR"

  # v1 : page originale
  sudo docker build -q -t localhost:5000/landing:v1 .
  sudo docker push localhost:5000/landing:v1
  ok "Image landing:v1 poussee"

  # v2 : titre modifie pour que le public voie la difference
  sed 's|<h1>.*</h1>|<h1>Version 2, deployee en 8 secondes.</h1>|' \
    index.html > /tmp/index-v2.html
  cp /tmp/index-v2.html index.html
  sudo docker build -q -t localhost:5000/landing:v2 .
  sudo docker push localhost:5000/landing:v2
  # Restaurer index.html v1
  git checkout -- index.html 2>/dev/null || \
    sed -i 's|<h1>Version 2, deployee en 8 secondes.</h1>|<h1>Votre application, en une commande.</h1>|' index.html
  ok "Image landing:v2 poussee"

  say "Etape 4 — Verification du catalogue registry"
  curl -s http://localhost:5000/v2/landing/tags/list
  echo ""

  say "Etape 5 — Pre-chauffe DNS"
  CODE=$(curl -s -o /dev/null -w '%{http_code}' "$URL")
  if [ "$CODE" = "404" ]; then
    ok "DNS OK, Traefik repond (404 attendu — pas encore d Ingress)"
  else
    warn "Reponse inattendue : HTTP $CODE"
  fi

  say "Preparation terminee. Lancer './deploy-demo.sh run' en direct."
}

# ------------------------------------------------------------------ run
run() {
  say "=== DEMO EN DIRECT ==="

  say "Etat initial"
  kubectl get ns

  say "Deploiement (commande unique)"
  source "$HOME/gandal-venv/bin/activate" 2>/dev/null || true
  cd "$HOME/gandal-paas"
  $DEPLOY deploy alice demo landing localhost:5000/landing:v1 80

  say "Attente des pods (Ctrl+C quand 2x 1/1 Running)"
  kubectl get pods -n project-alice-demo -w

  say "URL : $URL"
  say "Inspection"
  kubectl get all,ingress,quota,limitrange,networkpolicy -n project-alice-demo
  kubectl get pods -n project-alice-demo --show-labels
  $DEPLOY list --user alice

  say "Resilience — suppression des pods"
  kubectl delete pod -n project-alice-demo -l gandal.io/app=landing
  kubectl get pods -n project-alice-demo -w

  say "Mise a jour v1 -> v2"
  $DEPLOY deploy alice demo landing localhost:5000/landing:v2 80
  sleep 3 && kubectl get pods -n project-alice-demo -w

  say "Quotas — tentative de scale a 10"
  kubectl scale deployment landing -n project-alice-demo --replicas=10
  sleep 12
  kubectl get pods -n project-alice-demo
  kubectl get events -n project-alice-demo --field-selector reason=FailedCreate
  $DEPLOY deploy alice demo landing localhost:5000/landing:v2 80 --replicas 2
}

# ------------------------------------------------------------------ clean
clean() {
  say "Nettoyage"
  $DEPLOY delete alice demo --purge
  ok "project-alice-demo supprime"
  kubectl get ns
}

# ------------------------------------------------------------------ main
case "${1:-}" in
  prepare) prepare ;;
  run)     run ;;
  clean)   clean ;;
  *)
    echo "Usage : $0 [prepare|run|clean]"
    echo ""
    echo "  prepare  Purge, build images, verifie le socle (a faire la veille)"
    echo "  run      Sequence de demo en direct"
    echo "  clean    Supprime le namespace de demo apres la presentation"
    exit 1
    ;;
esac
