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
# Sur votre PC : créer la clé (si ce n'est pas déjà fait)
ssh-keygen -t ed25519 -f ~/.ssh/gandal -C "gandal-paas"
cat ~/.ssh/gandal.pub          # copier le contenu
```

Dans AWS CloudShell :

```bash
# Récupérer le dépôt sur la branche de fusion
git clone -b integration https://github.com/Djusse/gandal-paas.git
cd gandal-paas

# CloudShell crée sa propre clé : on réutilise la pubkey du PC, importée
# par le script. Si vous n'avez pas de clé sur votre PC, CloudShell a déjà
# généré ~/gandal et ~/gandal.pub : utilisez ~/gandal.pub à la place.
./infra/aws/provision-aws.sh up ~/.ssh/gandal.pub <IP_DE_VOTRE_PC>
```

Noter l'**Elastic IP** affichée. La région par défaut est `eu-west-3` (R7).

> `provision-aws.sh` importe la clé publique sous le nom `gandal-paas` et
> crée l'instance. La clé privée correspondante reste sur votre PC.
> L'IP passée en 3e argument est celle qui pourra se connecter en SSH et à
> l'API Kubernetes (ports 22 et 6443) ; 80/443 sont ouverts à tous.

---

## 2. Copier le dépôt et installer le socle

Le plus simple est de cloner directement sur la VM :

```bash
# Attendre que l'instance soit prête (1 à 2 min après le provisioning)
ssh -i ~/.ssh/gandal ubuntu@<IP>

git clone -b integration https://github.com/Djusse/gandal-paas.git
cd gandal-paas

# Docker, K3s, registry privé — 3 à 5 min
./infra/k3s/install.sh <IP>
```

Si le dépôt est privé ou si vous préférez copier l'arbre local :

```bash
# Depuis votre PC
rsync -av -e "ssh -i ~/.ssh/gandal" \
  --exclude '.git' --exclude '.venv' --exclude '__pycache__' \
  gandal-paas/ ubuntu@<IP>:/home/ubuntu/gandal-paas/
```

`install.sh` installe Docker, K3s, le registry `localhost:5000`, attend que
l'API Kubernetes réponde, puis vérifie que le registry répond sur le port 5000.
Il ajoute `KUBECONFIG` à `~/.bashrc` et `~/.profile`.

```bash
# Contrôle avant de continuer
kubectl get nodes            # 1 nœud Ready
curl -s localhost:5000/v2/   # {} attendu
```

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

# Le domaine dérive de l'IP publique de l'instance, pas de celle de CloudShell.
IP=$(curl -s https://checkip.amazonaws.com)
export BACKEND_URL="http://api.${IP}.sslip.io"
export GANDAL_BASE_DOMAIN="${IP}.sslip.io"
source .secrets/cluster.env      # ORCHESTRATOR_TOKEN, INTERNAL_TOKEN, WEBHOOK_SECRET

# Vérifier que l'API répond avant le test
curl -s "$BACKEND_URL/health"

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
export GANDAL_BASE_DOMAIN="${IP}.sslip.io"
export PYTHONPATH="$PWD/orchestrator"
source ~/gandal-venv/bin/activate        # fournit le client kubernetes

./orchestrator/validation.sh alice memoire my-api
```

Le script teste la CLI `orchestrator/gandal_deploy.py`, qui partage le même
code que le service HTTP. Le test 3 (isolation) ne peut plus être « ignoré » :
si la sonde `localhost:5000/curl:latest` manque, il échoue explicitement (R3).

> `validation.sh` déploie `localhost:5000/my-api:v1` par défaut. Pour utiliser
> l'image réellement publiée par l'installateur :
>
> ```bash
> export GANDAL_TEST_IMAGE=localhost:5000/paas/demo:a1b2c3d4
> ./orchestrator/validation.sh alice memoire my-api
> ```

---

## 5. Utiliser l'API

```bash
export API="http://api.${IP}.sslip.io"

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
| État d'un déploiement | `kubectl -n gandal-system exec deploy/orchestrator -- curl -s -H "X-Orchestrator-Token: $ORCHESTRATOR_TOKEN" localhost:8100/deployments/1` |
| Attente des pods | `kubectl get pods -n proj-<projet> -w` |
| Registry | `curl http://localhost:5000/v2/_catalog` et `curl http://localhost:5000/v2/paas/demo/tags/list` |
| Droits de l'orchestrateur | `kubectl auth can-i create deployments --as=system:serviceaccount:gandal-system:orchestrator -n proj-demo` |

Vérifications rapides, dans l'ordre :

```bash
# 1. Les trois pods tournent
kubectl -n gandal-system get pods

# 2. L'API répond
curl -s "http://api.${IP}.sslip.io/health"

# 3. L'orchestrateur voit Kubernetes
kubectl -n gandal-system exec deploy/orchestrator -- \
  curl -s localhost:8100/health

# 4. Les jetons concordent (même valeur des deux côtés)
kubectl -n gandal-system exec deploy/backend -- printenv ORCHESTRATOR_TOKEN
kubectl -n gandal-system exec deploy/orchestrator -- printenv ORCHESTRATOR_TOKEN

# 5. L'image est bien dans le registry
curl -s localhost:5000/v2/paas/demo/tags/list
```

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
