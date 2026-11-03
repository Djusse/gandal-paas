# Environnement d'intégration

Ce dossier contient l'environnement qui fait tourner le backend **et**
l'orchestrateur ensemble, ainsi que le test de bout en bout.

## Démarrage

```bash
cd deploy
cp .env.example .env          # ajuster si besoin
docker compose up -d --build  # db + backend (ORCHESTRATOR_MODE=mock)

# Avec un cluster (k3d en local, KUBECONFIG_PATH vers ~/.kube/config)
docker compose --profile cluster up -d --build
```

| Service | Port | Rôle |
|---|---|---|
| `db` | 5432 | PostgreSQL 16 (base du backend) |
| `backend` | 8000 | API FastAPI |
| `orchestrator` | 8100 | Service HTTP Kubernetes (profil `cluster`) |

Sans cluster, laissez le profil `cluster` désactivé : le backend utilise
`OrchestratorMock`, qui rappelle le backend après un court délai.

## Test de bout en bout

```bash
UP=1 ORCHESTRATOR_MODE=real ./deploy/e2e.sh
```

Le script :

1. crée un projet (`POST /projects`) ;
2. simule un webhook GitLab `success` ;
3. attend le statut `deployed` ;
4. vérifie que l'URL renvoie **HTTP 200** ;
5. supprime le projet.

### Scénario de résilience

```bash
RESILIENCE=1 UP=1 ORCHESTRATOR_MODE=real ./deploy/e2e.sh
```

L'orchestrateur est redémarré pendant le déploiement. Le projet doit tout de
même atteindre `deployed` : l'état vit dans Kubernetes et la boucle de
réconciliation reprend le suivi au redémarrage (D9).

### Variables

| Variable | Défaut | Rôle |
|---|---|---|
| `BACKEND_URL` | `http://localhost:8000` | Cible du test |
| `PROJECT` | `e2e-app-$$` | Nom de projet (unique par exécution) |
| `TIMEOUT` | `180` | Attente maximale du statut final |
| `RESILIENCE` | `0` | Redémarre l'orchestrateur en cours de déploiement |
| `UP` | `0` | Démarre `docker compose` avant le test |

## Sur AWS

```bash
GITLAB_MODE=fake ORCHESTRATOR_MODE=real BACKEND_URL=http://<IP>:8000 \
  ./deploy/e2e.sh
```

Le `GitLabFake` renvoie des images pointant vers le registry `localhost:5000`
du nœud K3s. Les 9 tests Kubernetes complémentaires sont dans
`orchestrator/validation.sh`.
