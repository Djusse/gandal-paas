# Déployer la plateforme fusionnée sur AWS

Ce guide reprend le parcours que vous avez suivi pour `gandal-paas`, en
ajoutant ce que la fusion apporte : le **backend** et l'**orchestrateur**
tournent désormais dans le cluster, et le déploiement d'une application
passe par l'API.

Durée : ~25 min (provisionnement + installation + tests).

---

## 0. Ce qui change par rapport à l'ancienne procédure

| Avant | Après |
|---|---|
| `gandal_deploy.py` lancé à la main sur la VM | service HTTP dans K3s, appelé par le backend |
| backend absent (ou lancé en local) | backend conteneurisé, PostgreSQL dans le cluster |
| `validation.sh` seul | `deploy/e2e.sh` **et** `validation.sh` |
| secrets vides | secrets générés une fois dans `.secrets/cluster.env` |

---

## 1. Préparer la clé et provisionner (CloudShell)

```bash
# Sur votre PC
ssh-keygen -t ed25519 -f ~/.ssh/gandal -C "gandal-paas"
cat ~/.ssh/gandal.pub          # à copier

# Dans AWS CloudShell, à la racine du dépôt cloné
./infra/aws/provision-aws.sh up ~/.ssh/gandal.pub <IP_DE_VOTRE_PC>
```

Noter l'**Elastic IP** affichée. La région par défaut est `eu-west-3` (R7).

> Si vous n'avez pas encore le dépôt dans CloudShell :
> `git clone https://github.com/Djusse/gandal-paas && cd gandal-paas`

---

## 2. Copier le dépôt et installer le socle

```bash
# Depuis votre PC
scp -i ~/.ssh/gandal -r gandal-paas ubuntu@<IP>:/home/ubuntu/

# Se connecter
ssh -i ~/.ssh/gandal ubuntu@<IP>

# Sur la VM : Docker, K3s, registry privé
cd ~/gandal-paas
./infra/k3s/install.sh <IP>
```

`install.sh` installe Docker, K3s, le registry `localhost:5000` et attend que
l'API Kubernetes réponde. Il ajoute aussi `KUBECONFIG` à `~/.bashrc`.

---

## 3. Installer la plateforme (backend + orchestrateur)

```bash
cd ~/gandal-paas
./infra/k3s/install-gandal.sh <IP>
```

Ce script est idempotent et fait tout le reste :

| Étape | Détail |
|---|---|
| Secrets | jetons aléatoires (`openssl`), base de données, écrits dans `.secrets/cluster.env` (ignoré par git) |
| Images | build + push de `gandal/backend`, `gandal/orchestrator`, `paas/demo:a1b2c3d4`, sonde `curl` |
| PostgreSQL | `infra/k3s/postgres.yaml`, volume `local-path` de 2 Gi |
| Orchestrateur | ServiceAccount + RBAC + Deployment + Service (port 8100) |
| Backend | ConfigMap + Deployment + Service (port 8000), `ORCHESTRATOR_MODE=real` |
| Ingress | API exposée sur `api.<IP>.sslip.io` |
| Vérification | `/health` du backend et de l'orchestrateur |

À la fin, le script affiche les commandes de test et le jeton du webhook.

```bash
kubectl -n gandal-system get pods
# backend-...            1/1 Running
# backend-db-...         1/1 Running
# orchestrator-...       1/1 Running
# private-registry-...   1/1 Running
```

---

## 4. Tester de bout en bout

```bash
cd ~/gandal-paas
export BACKEND_URL="http://api.$(curl -s https://checkip.amazonaws.com).sslip.io"
source .secrets/cluster.env

./deploy/e2e.sh
```

Attendu :

```text
==> POST /projects (e2e-app-...)
    OK : projet 1 (GitLab ...), namespace proj-e2e-app-...
==> Webhook pipeline success
    OK : pipeline ... enregistré (sha a1b2c3d4e5f6)
==> Attente du statut 'deployed'
    OK : statut deployed, URL http://e2e-app-....<IP>.sslip.io
==> Vérification HTTP de l'URL
    OK : HTTP 200 sur http://...
==> DELETE /projects/1
    OK : projet supprimé
==> E2E réussi
```

Le chemin réel est alors exercé : backend → orchestrateur (HTTP) → Kubernetes
(namespace, quota, isolation, Deployment, Service, Ingress) → rappel
`/internal/deployments/{id}/status` → URL qui répond 200.

### Résilience

```bash
RESILIENCE=1 ./deploy/e2e.sh
```

L'orchestrateur est redémarré pendant le déploiement ; le projet atteint quand
même `deployed` grâce à la boucle de réconciliation (D9).

### Les 9 tests Kubernetes

```bash
export KUBECONFIG=$HOME/.kube/config
export GANDAL_BASE_DOMAIN="<IP>.sslip.io"
./orchestrator/validation.sh alice memoire my-api
```

Le test 3 (isolation) ne peut plus être « ignoré » : si la sonde
`localhost:5000/curl:latest` manque, il échoue explicitement (R3).

---

## 5. Utiliser l'API

```bash
export API="http://api.<IP>.sslip.io"

# Créer un projet
curl -sS -X POST "$API/projects" \
  -H 'Content-Type: application/json' -H 'X-Dev-User: alice' \
  -d '{"name":"mon-app","app_port":8080}' | python3 -m json.tool

# Voir l'état et l'historique des déploiements
curl -sS "$API/projects/1" -H 'X-Dev-User: alice'
curl -sS "$API/projects/1/deployments" -H 'X-Dev-User: alice'

# Redéployer manuellement
curl -sS -X POST "$API/projects/1/deploy" -H 'X-Dev-User: alice'

# Supprimer (purge du namespace)
curl -sS -X DELETE "$API/projects/1" -H 'X-Dev-User: alice'
```

Documentation interactive : `http://api.<IP>.sslip.io/docs`.

---

## 6. Diagnostiquer

| Symptôme | Commande |
|---|---|
| Pod non prêt | `kubectl -n gandal-system describe pod <pod>` |
| Backend refuse un appel | `kubectl -n gandal-system logs deploy/backend --tail=50` |
| Orchestrateur et K8s | `kubectl -n gandal-system logs deploy/orchestrator --tail=50` |
| État d'un déploiement | `curl -H "X-Orchestrator-Token: $ORCHESTRATOR_TOKEN" http://localhost:8100/deployments/1` (depuis un pod) |
| Registry | `curl http://localhost:5000/v2/_catalog` |

Erreurs attendues et leur sens :

| Réponse | Cause |
|---|---|
| `401` sur `/deployments` | `ORCHESTRATOR_TOKEN` différent entre backend et orchestrateur |
| `422` sur `/deployments` | namespace réservé ou ≠ `proj-{project}` (garde-fou R12) |
| `503` sur `/deployments` | l'orchestrateur n'a pas pu charger le kubeconfig (`/health` → `kubernetes:false`) |
| Statut `failed` | image absente du registry : vérifier `curl localhost:5000/v2/paas/demo/tags/list` |

---

## 7. Arrêter (facturation)

```bash
# Dans CloudShell
./infra/aws/provision-aws.sh down
```

L'Elastic IP et le volume EBS sont facturés même instance arrêtée : `down`
supprime tout. Les secrets restent dans `.secrets/cluster.env` sur la VM, donc
perdus avec elle ; une réinstallation en régénère.

---

## Récapitulatif des fichiers utilisés

| Fichier | Rôle |
|---|---|
| [`infra/aws/provision-aws.sh`](../infra/aws/provision-aws.sh) | VPC, instance, Elastic IP, Security Group |
| [`infra/aws/open-sg.sh`](../infra/aws/open-sg.sh) | Ouvrir 22/6443 pour une nouvelle IP |
| [`infra/k3s/install.sh`](../infra/k3s/install.sh) | Docker, K3s, registry |
| [`infra/k3s/install-gandal.sh`](../infra/k3s/install-gandal.sh) | Secrets, images, PostgreSQL, orchestrateur, backend, Ingress |
| [`infra/k3s/postgres.yaml`](../infra/k3s/postgres.yaml) | Base du backend |
| [`infra/k3s/orchestrator.yaml`](../infra/k3s/orchestrator.yaml) | ServiceAccount, RBAC, Deployment |
| [`infra/k3s/backend.yaml`](../infra/k3s/backend.yaml) | ConfigMap, Deployment, Service |
| [`infra/k3s/backend-ingress.yaml`](../infra/k3s/backend-ingress.yaml) | Exposition de l'API |
| [`deploy/e2e.sh`](../deploy/e2e.sh) | Test de bout en bout |
| [`orchestrator/validation.sh`](../orchestrator/validation.sh) | 9 tests Kubernetes |
