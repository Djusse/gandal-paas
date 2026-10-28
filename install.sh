#!/usr/bin/env bash
# install.sh <IP_PUBLIQUE>
# Installation rejouable de la base GANDAL PaaS : Docker, K3s, registry prive.
# Teste pour Ubuntu 24.04/25.10. Autonome : ne depend d'aucun autre fichier.
set -euo pipefail

PUBLIC_IP="${1:?usage: ./install.sh <IP_PUBLIQUE>}"

# Sans cela, un paquet peut ouvrir une question debconf et bloquer le script.
export DEBIAN_FRONTEND=noninteractive

echo "==> Paquets de base"
# docker.io est dans universe : on s'assure que le depot est active.
if ! grep -qE '^[^#]*universe' /etc/apt/sources.list /etc/apt/sources.list.d/*.sources 2>/dev/null; then
  echo "    activation du depot universe"
  sudo add-apt-repository -y universe 2>/dev/null || \
    echo "    ATTENTION : depot universe introuvable, 'docker.io' peut manquer"
fi
sudo apt-get update
sudo apt-get install -y curl git docker.io python3-venv
sudo systemctl enable --now docker
# Le groupe docker ne s'applique qu'après reconnexion : utiliser 'sudo docker'
# ou 'newgrp docker' dans la session courante.
sudo usermod -aG docker "$USER"

# ---------------------------------------------------------------- swap
# Une instance de 1 ou 4 Go peut manquer de memoire pour K3s + registry.
# Un swap de 2 Go evite les OOM-kill sans changer le comportement du cluster.
if [ "$(free -m | awk '/^Mem:/{print $2}')" -lt 6000 ]; then
  if ! swapon --show | grep -q .; then
    echo "==> Memoire insuffisante : ajout de 2 Go de swap"
    sudo fallocate -l 2G /swapfile 2>/dev/null || \
      sudo dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile >/dev/null
    sudo swapon /swapfile
    grep -q '/swapfile' /etc/fstab || \
      echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  fi
  # K3s tolere mieux la pression memoire avec un seuil bas.
  echo "    RAM : $(free -h | awk '/^Mem:/{print $2}') + $(free -h | awk '/^Swap:/{print $2}') de swap"
fi

echo "==> Configuration du registry pour K3s (HTTP sur localhost:5000)"
sudo mkdir -p /etc/rancher/k3s
sudo tee /etc/rancher/k3s/registries.yaml >/dev/null <<'EOF'
mirrors:
  "localhost:5000":
    endpoint:
      - "http://localhost:5000"
EOF

echo "==> Installation de K3s"
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--tls-san ${PUBLIC_IP}" sh -

mkdir -p "$HOME/.kube"
sudo cp /etc/rancher/k3s/k3s.yaml "$HOME/.kube/config"
sudo chown "$USER":"$USER" "$HOME/.kube/config"
chmod 600 "$HOME/.kube/config"
export KUBECONFIG="$HOME/.kube/config"

# Ubuntu source ~/.bashrc dans les sessions SSH, MAIS le fichier par defaut
# sort immediatement si le shell n'est pas interactif : un export place en fin
# de fichier ne serait jamais atteint par "ssh hote 'kubectl ...'".
# On l'insere donc en tete, et on double dans ~/.profile.
if ! grep -q 'KUBECONFIG=' "$HOME/.bashrc" 2>/dev/null; then
  printf '%s\n' 'export KUBECONFIG="$HOME/.kube/config"' \
    | cat - "$HOME/.bashrc" > "$HOME/.bashrc.tmp" \
    && mv "$HOME/.bashrc.tmp" "$HOME/.bashrc"
fi
grep -q 'KUBECONFIG=' "$HOME/.profile" 2>/dev/null || \
  echo 'export KUBECONFIG="$HOME/.kube/config"' >> "$HOME/.profile"

# K3s peut mettre quelques secondes avant de declarer le noeud.
# Attente bornee : au-dela de 180 s on echoue explicitement au lieu de boucler
# indefiniment (le reste du script suppose un cluster fonctionnel).
echo "==> Attente de l'API Kubernetes (max 180 s)"
for _ in $(seq 1 60); do
  if kubectl get nodes >/dev/null 2>&1; then
    break
  fi
  sleep 3
done
if ! kubectl get nodes >/dev/null 2>&1; then
  echo "ERREUR : l'API Kubernetes ne repond pas apres 180 s." >&2
  echo "Diagnostic : sudo systemctl status k3s ; sudo journalctl -u k3s -n 50" >&2
  exit 1
fi
kubectl wait --for=condition=Ready nodes --all --timeout=180s

echo "==> Deploiement du registry prive"
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: Namespace
metadata:
  name: gandal-system
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: registry-pvc
  namespace: gandal-system
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 10Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: private-registry
  namespace: gandal-system
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: registry
  template:
    metadata:
      labels:
        app: registry
    spec:
      containers:
      - name: registry
        image: registry:2
        ports:
        - containerPort: 5000
          hostPort: 5000
        volumeMounts:
        - name: registry-storage
          mountPath: /var/lib/registry
      volumes:
      - name: registry-storage
        persistentVolumeClaim:
          claimName: registry-pvc
EOF
kubectl -n gandal-system rollout status deploy/private-registry --timeout=180s

# Verification reelle du registry : le conteneur peut etre "pret" alors que
# le port 5000 ne repond pas encore.
for _ in $(seq 1 30); do
  if curl -fsS http://localhost:5000/v2/ >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
if ! curl -fsS http://localhost:5000/v2/ >/dev/null 2>&1; then
  echo "ERREUR : le registry ne repond pas sur localhost:5000." >&2
  echo "Diagnostic : kubectl -n gandal-system logs deploy/private-registry" >&2
  exit 1
fi
echo "    registry OK sur http://localhost:5000"

echo "==> Environnement Python pour le script PaaS"
python3 -m venv "$HOME/gandal-venv"
"$HOME/gandal-venv/bin/pip" install --quiet kubernetes

echo
echo "Installation terminee."
echo "Reconnectez-vous (ou 'newgrp docker') pour utiliser docker sans sudo."
echo "Test registry : curl http://localhost:5000/v2/_catalog"
echo "Script PaaS   : source ~/gandal-venv/bin/activate && python gandal_deploy.py --help"
