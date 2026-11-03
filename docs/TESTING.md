# Tester soi-même

Trois niveaux, du plus rapide au plus complet. Aucune étape ne nécessite de
cluster pour les deux premiers.

---

## 1. Tout vérifier en une commande (~1 min)

Depuis la racine du dépôt :

```bash
cd gandal-paas
./deploy/verify-local.sh
```

Le script crée `.venv/`, installe les dépendances, puis exécute :

| Étape | Ce qui est vérifié |
|---|---|
| Tests unitaires | 37 backend + 58 orchestrateur |
| Style | `ruff` sur les deux projets |
| Documentation | liens Markdown, manifestes YAML, anciens chemins |
| PostgreSQL | 5 tests d'isolation transactionnelle (**R1**) |
| Bout en bout | création → webhook → `deployed` → suppression (mode mock) |

Sortie attendue :

```text
  réussis : 12   échecs : 0
Validation locale réussie.
```

Options :

```bash
./deploy/verify-local.sh --fast        # sans PostgreSQL ni e2e
PG_IMAGE=postgres:9.6-alpine ./deploy/verify-local.sh   # image déjà présente
PG_URL=postgresql+psycopg://user:pass@host:5432/base ./deploy/verify-local.sh
```

> Si l'image `postgres:16-alpine` n'est pas téléchargeable, utilisez
> `PG_IMAGE` avec une image locale (`docker images postgres`).

---

## 2. Manuellement, étape par étape

### Tests seuls

```bash
cd gandal-paas

python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt -r orchestrator/requirements-dev.txt

cd backend && pytest -q && cd ..
cd orchestrator && pytest -q && cd ..
```

Résultats attendus : `37 passed` puis `58 passed` (5 `skipped` côté backend
sans base PostgreSQL, ce sont les tests d'intégration).

### Historique de la fusion

```bash
git log --oneline | head -5
git shortlog -sn --no-merges HEAD          # 3 auteurs
git log --follow --oneline -- backend/app/main.py   # historique d'origine
```

### PostgreSQL (correction R1)

```bash
./deploy/test-postgres.sh
```

Le script lance `postgres` dans Docker sur le port 55432, exécute la suite
unitaire puis les tests d'intégration, et supprime le conteneur.

### Backend seul

```bash
cd gandal-paas/backend
cp .env.example .env          # ajuster si besoin
uvicorn app.main:app --reload
```

Puis, dans un autre terminal :

```bash
# Créer un projet
curl -sS -X POST http://localhost:8000/projects \
  -H 'Content-Type: application/json' -H 'X-Dev-User: alice' \
  -d '{"name":"ma-demo","app_port":8080}' | python3 -m json.tool

# Simuler un pipeline réussi (tag = 8 premiers caractères du sha)
curl -sS -X POST http://localhost:8000/webhooks/gitlab \
  -H 'Content-Type: application/json' -H 'X-Gitlab-Token: change-me-long-random' \
  -d '{"object_kind":"pipeline","project":{"id":1},
       "object_attributes":{"id":1,"status":"success","sha":"a1b2c3d4e5f6","ref":"main"}}'

# Suivre le déploiement
curl -sS http://localhost:8000/projects/1/deployments -H 'X-Dev-User: alice'
```

Sous `ORCHESTRATOR_MODE=mock`, le statut passe à `deployed` en ~3 s.

Documentation interactive : <http://localhost:8000/docs>

### Orchestrateur seul (garde-fous)

```bash
cd gandal-paas/orchestrator
pip install -r requirements-dev.txt

ORCHESTRATOR_TOKEN=mon-jeton INTERNAL_TOKEN=interne \
KUBECONFIG=/inexistant \
uvicorn app.main:app --port 8100
```

```bash
# Santé : kubernetes=false sans cluster, l'application reste debout
curl -s http://localhost:8100/health

# Sans jeton -> 401
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8100/deployments \
  -H 'Content-Type: application/json' -d '{}'

# Namespace réservé -> refusé (422) dès que le service est initialisé
curl -s -X POST http://localhost:8100/deployments \
  -H 'Content-Type: application/json' -H 'X-Orchestrator-Token: mon-jeton' \
  -d '{"deployment_id":1,"project":"mon-app","namespace":"kube-system",
       "image":"r/a","port":80,"replicas":2}'
```

Sans cluster, les routes de déploiement répondent `503` : c'est le
comportement attendu, `/health` l'indique (`kubernetes: false`).

---

## 3. Avec un cluster (k3d, k3s, kind)

### Développement local

```bash
k3d cluster create gandal
cd gandal-paas/deploy
cp .env.example .env
ORCHESTRATOR_MODE=real docker compose --profile cluster up -d --build

# Dans un autre terminal
ORCHESTRATOR_MODE=real ./e2e.sh          # attend HTTP 200 sur l'URL
RESILIENCE=1 ORCHESTRATOR_MODE=real ./e2e.sh   # redémarre l'orchestrateur
```

### Sur la VM AWS

```bash
infra/aws/provision-aws.sh up ~/.ssh/gandal.pub
infra/k3s/install.sh <IP_PUBLIQUE>
kubectl apply -f infra/k3s/orchestrator.yaml
infra/aws/run-validation.sh <IP_PUBLIQUE>        # 9 tests Kubernetes
```

Le test 3 (isolation) exige l'image `localhost:5000/curl:latest` publiée dans
le registry ; sans elle, le script échoue explicitement au lieu de l'ignorer.

---

## Ce qui ne peut pas être testé sans cluster

| Élément | Pourquoi |
|---|---|
| `orchestrator/validation.sh` | interroge l'API Kubernetes |
| `e2e.sh` avec `ORCHESTRATOR_MODE=real` | applique de vraies ressources |
| Scénario de résilience | redémarre un pod |
| Isolation réseau, quotas, Ingress | objets Kubernetes |

Tout le reste est couvert par `verify-local.sh`.
