# 📚 Index de la documentation GANDAL PaaS

Bienvenue dans le projet GANDAL PaaS. Ce fichier recense les documents
réellement présents dans `docs/` et renvoie vers les zones du monorepo.

> Ce fichier décrit l'arborescence **après fusion** des dépôts
> `9ball9999/paas` (backend) et `Djusse/gandal-paas` (infra).

---

## 🚀 Démarrage rapide

1. **[../README.md](../README.md)** — vue d'ensemble du monorepo et démarrage.
2. **[ARCHITECTURE.md](ARCHITECTURE.md)** — architecture du socle Kubernetes.
3. **[VALIDATION_REPORT.md](VALIDATION_REPORT.md)** — rapport de validation (voir
   la réserve du plan sur le test d'isolation, R3).
4. **[../backend/README.md](../backend/README.md)** — API FastAPI.
5. **[../orchestrator/README.md](../orchestrator/README.md)** — service orchestrateur.

---

## 📖 Documentation principale

| Document | Description |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Composants, flux, quotas, isolation réseau |
| [README-infra.md](README-infra.md) | Guide d'installation et d'exploitation de l'infra (ex-`README.md` racine) |
| [VALIDATION_REPORT-V2.md](VALIDATION_REPORT-V2.md) | **Rapport de la phase de fusion** (état actuel) |
| [VALIDATION_REPORT.md](VALIDATION_REPORT.md) | Rapport historique de la simulation initiale |
| [STATUS.md](STATUS.md) | État du déploiement (document historique) |
| [NEXT_STEPS.md](NEXT_STEPS.md) | Étapes après la première mise en service (historique) |
| [PRESENTATION.md](PRESENTATION.md) | Support de présentation du projet |
| [DEMO_LANDING_PAGE.md](DEMO_LANDING_PAGE.md) | Scénario de démonstration (landing page) |
| [MIGRATION.md](MIGRATION.md) | Procédure de bascule, étiquetage et archivage |
| [DEPLOY-AWS.md](DEPLOY-AWS.md) | Déploiement complet sur AWS : CloudShell → K3s → e2e |
| [TESTING.md](TESTING.md) | Comment tester soi-même (local, sans cluster, avec cluster) |
| [INDEX.md](INDEX.md) | Ce fichier |

### Documents LaTeX

| Document | Description |
|---|---|
| [explication_v3.tex](explication_v3.tex) | Cadrage : périmètre, état final, tests attendus |
| [simulation_v3.tex](simulation_v3.tex) | Procédure d'implémentation (phases 1 à 9) |

Génération : `cd docs && pdflatex explication_v3.tex` (deux passes).

### Contrats

| Document | Description |
|---|---|
| [contracts/deployment-request.schema.json](contracts/deployment-request.schema.json) | Requête `POST /deployments` (backend → orchestrateur) |
| [contracts/deployment-status.schema.json](contracts/deployment-status.schema.json) | Rappel `POST /internal/deployments/{id}/status` |
| [contracts/deployment-read.schema.json](contracts/deployment-read.schema.json) | Réponse `GET /deployments/{id}` |

---

## 🛠️ Code et scripts

### Backend — `backend/`

| Élément | Description |
|---|---|
| `backend/app/` | API FastAPI : routeurs, services, ports et adaptateurs |
| `backend/tests/` | Suite `pytest` (11 tests à l'origine) |
| `backend/Dockerfile`, `backend/docker-compose.yml` | Conteneurisation locale du backend |

### Orchestrateur — `orchestrator/`

| Élément | Description |
|---|---|
| `orchestrator/gandal/k8s.py` | Traduction d'une demande de déploiement en ressources Kubernetes |
| `orchestrator/gandal/service.py` | Service HTTP (validation, idempotence, rappels) |
| `orchestrator/app/` | Application FastAPI de l'orchestrateur |
| `orchestrator/gandal_deploy.py` | CLI compatible avec l'ancien script |
| `orchestrator/validation.sh` | Les 9 tests de validation (ex-`tests/validation.sh`) |
| `orchestrator/tests/` | Tests unitaires (client Kubernetes simulé) |

### Infrastructure — `infra/`

| Élément | Description |
|---|---|
| `infra/k3s/install.sh` | Installation rejouable de Docker, K3s et du registry |
| `infra/k3s/registry.yaml` | Manifeste du registry privé |
| `infra/k3s/orchestrator.yaml` | Déploiement de l'orchestrateur, ServiceAccount et RBAC |
| `infra/aws/provision-aws.sh` | Création/destruction de l'infra AWS |
| `infra/aws/open-sg.sh` | Ouverture du Security Group pour une IP |
| `infra/aws/add-pc-key.sh` | Ajout d'une clé publique sur la VM |
| `infra/aws/repair-access.sh` | Réparation de l'accès SSH |
| `infra/aws/ssh-kubectl.sh` | Exécution de `kubectl` à distance |
| `infra/aws/deploy-alice.sh` | Déploiement de l'application de test |
| `infra/aws/run-validation.sh` | Exécution des tests de validation sur la VM |
| `infra/aws/deploy-demo.sh` | Séquence complète de démonstration |

### Intégration — `deploy/`

| Élément | Description |
|---|---|
| `deploy/docker-compose.yml` | db PostgreSQL + backend (+ orchestrateur local) |
| `deploy/e2e.sh` | Test de bout en bout (création → déploiement → HTTP 200) |

### Démonstration — `demo/`

| Élément | Description |
|---|---|
| `demo/Dockerfile`, `demo/index.html` | Image de démonstration (`landing`) |

---

## 📊 Diagrammes

Tous les diagrammes sont dans [`diagrams/`](diagrams/), avec un index dédié :
[`diagrams/INDEX-DIAGRAMMES.md`](diagrams/INDEX-DIAGRAMMES.md).

| Série | Fichiers |
|---|---|
| Architecture simple | `01-architecture-simple.puml`, `02-k3s-namespaces.puml` |
| Flux | `03-flux-deploiement-simple.puml`, `04-flux-http-simple.puml` |
| Sécurité et quotas | `05-isolation-reseau.puml`, `06-quotas.puml` |
| Architecture V2 | `07-architecture-globale-v2.puml` … `12-quotas-v2.puml` |

Génération : `cd docs/diagrams && plantuml *.puml`.

---

## 📐 Structure du dépôt

```text
gandal-paas/
├── backend/           # API FastAPI (ex 9ball9999/paas)
├── orchestrator/      # Service HTTP + module Kubernetes + validation.sh
├── infra/
│   ├── k3s/           # install.sh, registry.yaml, orchestrator.yaml
│   └── aws/           # Provisionnement et démonstration
├── deploy/            # docker-compose d'intégration + e2e.sh
├── docs/              # Documentation, diagrammes, contrats, LaTeX
├── demo/              # Image de démonstration
├── .github/workflows/ # CI
├── plan V2.md         # Plan de fusion (référence)
└── README.md
```

---

## 🎯 Par cas d'usage

### Comprendre l'architecture

1. [../README.md](../README.md) — vue d'ensemble et schéma de flux.
2. [ARCHITECTURE.md](ARCHITECTURE.md) — détail des composants.
3. [diagrams/](diagrams/) — représentations visuelles.

### Déployer sur AWS

1. `infra/aws/provision-aws.sh up ~/.ssh/gandal.pub`
2. `infra/k3s/install.sh <IP_PUBLIQUE>`
3. `infra/aws/deploy-alice.sh <IP_PUBLIQUE>`
4. `infra/aws/run-validation.sh <IP_PUBLIQUE>`
5. `infra/aws/provision-aws.sh down`

### Développer en local

```bash
cd deploy && docker compose up -d
cd backend && pytest -q
cd orchestrator && pytest -q
```

### Valider que tout fonctionne

1. `deploy/e2e.sh` — test de bout en bout.
2. `orchestrator/validation.sh` — 9 tests Kubernetes sur la VM.
3. `backend/tests/` et `orchestrator/tests/` — suites unitaires.

---

## 🔗 Liens externes

- [Kubernetes](https://kubernetes.io/docs/)
- [K3s](https://docs.k3s.io/)
- [Traefik](https://doc.traefik.io/traefik/)
- [PlantUML](https://plantuml.com/)
- [sslip.io](https://sslip.io/)

---

## 📝 Glossaire

| Terme | Définition |
|---|---|
| **PaaS** | Platform as a Service |
| **K3s** | Distribution Kubernetes légère |
| **Namespace** | Isolation logique dans Kubernetes (`proj-{nom}`) |
| **Ingress** | Routeur HTTP exposant les applications |
| **ResourceQuota** | Plafond de ressources par projet |
| **NetworkPolicy** | Pare-feu réseau Kubernetes |
| **Orchestrateur** | Service HTTP qui applique les ressources Kubernetes |
| **sslip.io** | DNS wildcard automatique dérivé d'une IP |

---

## ✅ Checklist de mise en service

- [ ] Générer la clé SSH (`ssh-keygen`)
- [ ] Provisionner AWS (`infra/aws/provision-aws.sh up`)
- [ ] Installer K3s et le registry (`infra/k3s/install.sh`)
- [ ] Déployer l'orchestrateur (`infra/k3s/orchestrator.yaml`)
- [ ] Démarrer le backend (`deploy/docker-compose.yml`)
- [ ] Publier les images de test (`nginx`, `curl`)
- [ ] Déployer et valider (`infra/aws/deploy-alice.sh`, `infra/aws/run-validation.sh`)
- [ ] Détruire l'infra (`infra/aws/provision-aws.sh down`)

---

**Bonne lecture et bon développement.**
