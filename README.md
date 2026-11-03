# GANDAL PaaS

Plateforme-as-a-Service du projet GANDAL : une API qui transforme « un dépôt Git »
en application accessible par URL, sur un cluster K3s.

Ce dépôt est le **monorepo** issu de la fusion de :

- `9ball9999/paas` — le **plan de contrôle** (API FastAPI, base de données, webhooks GitLab) ;
- `Djusse/gandal-paas` — le **plan d'exécution** (K3s, registry privé, création des ressources Kubernetes).

Le plan de fusion détaillé, les décisions (D1–D9) et les risques sont dans
[`PLAN-FUSION-V2.md`](docs/PLAN-FUSION-V2.md).

---

## Architecture

```text
Étudiant ─ POST /projects ──▶ backend ──▶ GitLab (dépôt + webhook)
   git push ──▶ GitLab CI (Kaniko) ──▶ image dans le registry
GitLab ─ webhook pipeline ──▶ backend ── POST /deployments ──▶ ORCHESTRATEUR ──▶ K3s
backend ◀── POST /internal/deployments/{id}/status (X-Internal-Token) ── ORCHESTRATEUR
                                                       statut « deployed » + URL
```

| Composant | Rôle | Emplacement |
|---|---|---|
| **backend** | API REST : projets, images, déploiements, webhooks, callbacks internes | [`backend/`](backend/) |
| **orchestrateur** | Traduit une demande de déploiement en ressources Kubernetes et rappelle le backend | [`orchestrator/`](orchestrator/) |
| **infra** | Installation K3s/registry, provisionnement AWS, RBAC de l'orchestrateur | [`infra/`](infra/) |
| **deploy** | Environnement d'intégration (PostgreSQL + backend + orchestrateur) et test de bout en bout | [`deploy/`](deploy/) |
| **docs** | Architecture, rapports, diagrammes, contrats, documents LaTeX | [`docs/`](docs/) |
| **demo** | Image de démonstration (`landing`) | [`demo/`](demo/) |

Conventions (décision D3) :

- namespace Kubernetes : `proj-{nom}` (calculé par le backend, jamais par l'orchestrateur) ;
- URL publique : `{nom}.{GANDAL_BASE_DOMAIN}` (`<IP>.sslip.io` sur AWS) ;
- labels : `gandal.io/owner`, `gandal.io/project`, `gandal.io/app`, `gandal.io/managed` ;
- noms de projet **globalement uniques**, minuscules, sans tiret final
  (`^[a-z][a-z0-9-]{1,28}[a-z0-9]$`) ;
- réplicas par défaut : **2** (D8), quota de 4 pods par projet.

---

## Démarrage rapide — développement local

### Tout vérifier en une commande

```bash
./deploy/verify-local.sh
```

Cette commande crée `.venv/`, installe les dépendances et enchaîne : tests
unitaires (37 backend + 58 orchestrateur), `ruff`, liens Markdown, manifestes
YAML, tests PostgreSQL (R1) et un bout en bout en mode mock. **Aucun cluster
n'est nécessaire.** Détail et options : [`docs/TESTING.md`](docs/TESTING.md).

### Lancer les services

```bash
cd deploy && cp .env.example .env
docker compose up -d --build
curl -s http://localhost:8000/health
```

Le backend démarre par défaut avec `GITLAB_MODE=fake` et `ORCHESTRATOR_MODE=mock` :
aucun GitLab ni cluster n'est requis. Pour brancher le vrai orchestrateur, voir
[`deploy/README.md`](deploy/README.md).

---

## Déploiement sur Kubernetes (simulation AWS)

```bash
# Création de l'infrastructure AWS (CloudShell)
infra/aws/provision-aws.sh up ~/.ssh/gandal.pub

# Sur la VM : Docker, K3s et registry privé
infra/k3s/install.sh <IP_PUBLIQUE>

# Orchestrateur dans le cluster (ServiceAccount + RBAC + Service)
kubectl apply -f infra/k3s/orchestrator.yaml

# Démonstration et validation
infra/aws/deploy-demo.sh prepare
infra/aws/run-validation.sh <IP_PUBLIQUE>
```

Les 9 tests Kubernetes de `orchestrator/validation.sh` valident le déploiement
automatisé, l'accès DNS, l'isolation réseau, la résilience, les quotas, les
métriques, l'identification des pods, l'idempotence et le nettoyage.

Détails : [`docs/README-infra.md`](docs/README-infra.md).

---

## Contrat backend ↔ orchestrateur

`POST /deployments` (en-tête `X-Orchestrator-Token`) :

```json
{
  "deployment_id": 42,
  "project": "mon-app",
  "owner": "alice",
  "namespace": "proj-mon-app",
  "image": "registry.example/paas/mon-app",
  "tag": "a1b2c3d4",
  "digest": "sha256:…",
  "port": 8080,
  "replicas": 2
}
```

→ `202 {"deployment_ref": "orch-42"}`, une fois les ressources appliquées.

`GET /deployments/42` → `{"status": "...", "url": "...", "message": "..."}`.
Rappel : `POST {BACKEND_URL}/internal/deployments/42/status` avec `X-Internal-Token`.

Schémas JSON versionnés : [`docs/contracts/`](docs/contracts/).

---

## Tests et qualité

```bash
# Backend
cd backend && pytest -q && ruff check app tests

# Orchestrateur
cd orchestrator && pytest -q && ruff check gandal app tests

# Scripts
shellcheck infra/k3s/*.sh infra/aws/*.sh orchestrator/validation.sh deploy/*.sh

# Bout en bout (cluster disponible)
deploy/e2e.sh
```

La CI GitHub Actions (`.github/workflows/ci.yml`) exécute `pytest`, `ruff`,
`shellcheck` et un contrôle qu'aucun ancien chemin ne subsiste.

---

## Documentation

- [`docs/INDEX.md`](docs/INDEX.md) — index complet.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — architecture Kubernetes.
- [`docs/VALIDATION_REPORT.md`](docs/VALIDATION_REPORT.md) — rapport historique.
- [`backend/README.md`](backend/README.md) — API.
- [`orchestrator/README.md`](orchestrator/README.md) — orchestrateur.

---

## Licence

Voir [`LICENSE`](LICENSE). Les contributions sont décrites dans
[`CONTRIBUTING.md`](CONTRIBUTING.md).
