# Orchestrateur GANDAL PaaS

Service HTTP qui transforme une demande de déploiement en ressources
Kubernetes, puis rapporte l'état au backend.

Il remplace la CLI `gandal_deploy.py` d'origine : celle-ci reste disponible
pour la compatibilité avec [`validation.sh`](validation.sh), mais toute la
logique vit désormais dans le paquet [`gandal/`](gandal/).

## Contenu

| Chemin | Rôle |
|---|---|
| `gandal/config.py` | Configuration par variables d'environnement |
| `gandal/names.py` | Validation DNS-1123, normalisation des labels, garde-fous |
| `gandal/k8s.py` | Application des ressources (namespace, quotas, isolation, Deployment, Service, Ingress) |
| `gandal/service.py` | Règles métier : idempotence, lecture d'état, boucle de réconciliation |
| `gandal/notifier.py` | Rappels vers `POST /internal/deployments/{id}/status` |
| `app/` | Application FastAPI (routes, schémas, dépendances) |
| `gandal_deploy.py` | CLI : `deploy`, `list`, `status`, `delete` |
| `validation.sh` | Les 9 tests Kubernetes sur la VM |
| `tests/` | Tests unitaires, API, contrats et garde-fous |

## Démarrage local

```bash
pip install -r requirements-dev.txt
pytest -q

# Contre un cluster accessible (k3d, k3s, kind…)
export KUBECONFIG=$HOME/.kube/config
export GANDAL_BASE_DOMAIN=$(hostname -I | awk '{print $1}').sslip.io
uvicorn app.main:app --host 0.0.0.0 --port 8100
```

Sans cluster, l'application démarre quand même : `/health` répond avec
`kubernetes: false` et les routes de déploiement renvoient `503`.

## API

| Route | Rôle |
|---|---|
| `POST /deployments` | Applique les ressources, répond `202` une fois Kubernetes informé |
| `GET /deployments/{id}` | État courant lu dans Kubernetes (repli du backend) |
| `DELETE /projects/{namespace}` | Purge d'un namespace applicatif |
| `GET /health` | Sonde de vie |

Toutes les routes de déploiement exigent l'en-tête `X-Orchestrator-Token`.

```bash
curl -sS -X POST http://localhost:8100/deployments \
  -H 'Content-Type: application/json' \
  -H 'X-Orchestrator-Token: dev-orchestrator-token' \
  -d '{
        "deployment_id": 42,
        "project": "mon-app",
        "owner": "alice",
        "namespace": "proj-mon-app",
        "image": "localhost:5000/paas/mon-app",
        "tag": "a1b2c3d4",
        "digest": null,
        "port": 8080,
        "replicas": 2
      }'
```

Schémas complets : [`../docs/contracts/`](../docs/contracts/).

## Fonctionnement

```text
POST /deployments
   └─ DeploySpec.from_payload    validation (nom, namespace, port, réplicas)
   └─ KubernetesBackend.apply    namespace → LimitRange → ResourceQuota
                                 → NetworkPolicy → Deployment → Service → Ingress
   └─ 202 {deployment_ref: "orch-42"}

Boucle de réconciliation (toutes les 30 s)
   └─ liste les Deployment portant gandal.io/managed=true
   └─ lit l'état (ready replicas, ProgressDeadlineExceeded, délai)
   └─ si l'état final diffère de gandal.io/reported-status :
        POST {BACKEND_URL}/internal/deployments/{id}/status
        puis annotation gandal.io/reported-status = deployed|failed
```

Aucun état n'est stocké hors de Kubernetes : un redémarrage du service ne perd
aucun déploiement accepté (décision D9).

## Conventions appliquées (D3)

- namespace : `proj-{project}`, calculé par le backend et **vérifié** ici ;
- URL : `{project}.{GANDAL_BASE_DOMAIN}` ;
- labels : `gandal.io/owner` (normalisé), `gandal.io/project`, `gandal.io/app`,
  `gandal.io/managed` ;
- annotations : `gandal.io/deployment-id`, `gandal.io/image`, `gandal.io/url`,
  `gandal.io/reported-status` ;
- image déployée : `repository@digest` si le digest est connu, sinon
  `repository:tag`.

## Garde-fous (R12)

Un jeton interne valide n'autorise pas n'importe quel namespace :

| Cas | Réponse |
|---|---|
| `namespace` dans `kube-system`, `kube-public`, `kube-node-lease`, `default`, `gandal-system` | `422` |
| `namespace` ≠ `proj-{project}` | `422` |
| `namespace` sans préfixe `proj-` | `422` |
| suppression d'un namespace sans `gandal.io/managed=true` | `422` |
| nom non DNS-1123 (majuscules, `_`, tiret final, > 63 car.) | `422` |

## Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `GANDAL_BASE_DOMAIN` | `gandal.test` | Domaine des URLs |
| `GANDAL_INGRESS_CLASS` | `traefik` | Classe d'Ingress |
| `GANDAL_REPLICAS` | `2` | Réplicas par défaut (D8) |
| `GANDAL_QUOTA_*` | 1 CPU / 1Gi / 2 CPU / 2Gi / 4 pods | Quota par projet |
| `GANDAL_CTR_*` | 100m / 128Mi / 500m / 512Mi | Ressources du conteneur |
| `GANDAL_RECONCILE_INTERVAL` | `30` | Période de réconciliation (s) |
| `GANDAL_ROLLOUT_TIMEOUT` | `300` | Délai avant `failed` (s) |
| `GANDAL_CALLBACK_ATTEMPTS` | `5` | Tentatives de rappel |
| `GANDAL_CALLBACK_BACKOFF` | `2` | Attente croissante (s) |
| `ORCHESTRATOR_TOKEN` | `change-me-long-random` | Jeton entrant |
| `INTERNAL_TOKEN` | `change-me-long-random` | Jeton du rappel backend |
| `BACKEND_URL` | `http://localhost:8000` | Cible des rappels |
| `GANDAL_IN_CLUSTER` | `false` | Force `load_incluster_config` |
| `KUBECONFIG` | — | Chemin du kubeconfig hors cluster |

## Déploiement dans K3s

```bash
kubectl apply -f ../infra/k3s/orchestrator.yaml
# ou, si les droits par namespace sont trop lourds sur K3s :
kubectl apply -f ../infra/k3s/orchestrator-clusterrole.yaml
```

Le manifeste crée le ServiceAccount `orchestrator`, le ConfigMap et le Secret
de configuration, puis le Deployment et le Service sur le port 8100.

## Validation sur la VM

```bash
export KUBECONFIG=$HOME/.kube/config
export GANDAL_BASE_DOMAIN=<IP>.sslip.io
./validation.sh alice memoire my-api
```

Le test 3 (isolation réseau) échoue explicitement si l'image de sonde
`localhost:5000/curl:latest` n'est pas publiée : plus de faux « 9/9 » (R3).
