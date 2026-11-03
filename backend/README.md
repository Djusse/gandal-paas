# GANDAL PaaS — Service Backend & Orchestrateur d'Intégration

Ce dépôt héberge le **service Backend du PaaS GANDAL** (*Platform as a Service* universitaire). Conçu selon les principes de l'**Architecture Hexagonale (Ports et Adaptateurs)**, il agit comme la tour de contrôle centrale reliant le **Portail Étudiant**, l'instance **GitLab & Registry**, le moteur **CI/CD Kaniko**, et l'**Orchestrateur Kubernetes**.

---

## 1. Vue d'Ensemble & Fonctionnement du PaaS

Le système permet aux étudiants de déployer leurs applications conteneurisées dans des environnements Kubernetes isolés via une expérience inspirée de Heroku ou Render :

```
[Portail Étudiant]  <--->  [PaaS Backend]  <--->  [GitLab & Registry]
                                 |
                                 v
                     [Orchestrateur Kubernetes]  --->  Application en ligne
```

### Les 4 Acteurs Clés du Système
1. **L'Étudiant (Portail Développeur)** :
   - Crée son projet via l'interface (ex: `mon-application`).
   - Reçoit immédiatement l'URL d'un dépôt Git vierge dédié.
   - Pousse son code (`git push origin main`).
   - Suit en temps réel l'évolution du statut (`awaiting_push` → `building` → `deploying` → `deployed`).
2. **GitLab & CI/CD** :
   - Héberge le code source de l'étudiant.
   - Déclenche un pipeline partagé (`templates/build.yml@paas/ci-templates`) exécuté sur un runner isolé avec **Kaniko** (aucun montage du socket Docker hôte pour garantir la sécurité multi-tenant).
   - Envoie des webhooks sécurisés au backend lors des changements d'état du pipeline.
3. **Le Backend PaaS (Ce Répertoire)** :
   - Coordonne le cycle de vie complet.
   - Enregistre et valide les métadonnées dans PostgreSQL (projets, événements de pipeline, images construites, déploiements).
   - Valide les webhooks GitLab par signature HMAC et garantit l'idempotence des événements.
   - Récupère le digest de l'image conteneur et ordonne le déploiement.
4. **L'Orchestrateur Kubernetes** :
   - Déploie le conteneur dans un namespace Kubernetes dédié et étanche (`proj-{nom}`).
   - Configure le Service K8s, l'Ingress / Gateway API et le DNS local.
   - Notifie le Backend PaaS avec l'URL publique finale (`http://{nom}.apps.gandal.local`).

---

## 2. Architecture Hexagonale (Ports & Adaptateurs)

Afin de permettre un développement et des tests découplés des équipes d'infrastructure ou de GitLab, toute la logique métier s'appuie sur des interfaces abstraites (**Ports**) pouvant être associées à des **Adaptateurs** virtuels (fakes/mocks) ou réels :

| Dépendance | Équipe Propriétaire | Mode Développement | Mode Production | Variable d'Environnement |
|---|---|---|---|---|
| **GitLab & Registry** | Équipe GitLab | `GitLabFake` (en mémoire / simulation) | `GitLabReal` (API REST v4 GitLab) | `GITLAB_MODE=fake\|real` |
| **Runner & Template CI** | Équipe CI/CD | `scripts/simulate_webhook.py` | Runner VM GitLab réel | *(déclenché par git push)* |
| **Orchestrateur K8s** | Équipe Orchestrateur | `OrchestratorMock` (callback asynchrone) | `OrchestratorReal` (POST HTTP) | `ORCHESTRATOR_MODE=mock\|real` |
| **Authentification** | Équipe GitLab / Auth | En-tête de dev `X-Dev-User` | Jeton Bearer OAuth GitLab | `AUTH_MODE=dev\|oauth` |
| **Infrastructure K8s** | Équipe Infra | Non requise en dev | Gérée par l'Orchestrateur | *(transparent)* |

Le passage d'un environnement de mock au système réel en production se fait **uniquement par modification des variables d'environnement**, sans modifier la moindre ligne de code métier.

---

## 3. Structure du Projet

```
paas-backend/
├── app/
│   ├── adapters/                     # Implémentations concrètes des ports
│   │   ├── gitlab_fake.py            # Simulation GitLab en mémoire
│   │   ├── gitlab_real.py            # Client API REST GitLab v4 officiel
│   │   ├── orchestrator_mock.py      # Mock simulant le déploiement K8s asynchrone
│   │   └── orchestrator_real.py      # Client HTTP pour l'Orchestrateur réel
│   ├── routers/                      # Contrôleurs HTTP FastAPI
│   │   ├── health.py                 # GET /health (vérification de santé de l'API et de la DB)
│   │   ├── projects.py               # CRUD projets, historique des builds, images et redéploiement
│   │   ├── webhooks.py               # POST /webhooks/gitlab (vérification HMAC, déduplication)
│   │   └── internal.py               # POST /internal/deployments/{id}/status (callback tokenisé)
│   ├── services/                     # Logique métier & cas d'usage
│   │   ├── project_service.py        # Gestion du cycle de vie des projets & autorisations
│   │   └── build_service.py          # Tâches asynchrones (liaison SHA -> Image -> Déploiement)
│   ├── config.py                     # Gestion des paramètres via Pydantic Settings
│   ├── db.py                         # Configuration du moteur SQLAlchemy (Postgres / SQLite)
│   ├── deps.py                       # Injection de dépendances FastAPI (Auth, Adaptateurs)
│   ├── main.py                       # Point d'entrée de l'application FastAPI
│   ├── models.py                     # Modèles ORM (Project, PipelineEvent, Image, Deployment)
│   ├── ports.py                      # Définition des protocoles abstraits (GitLabPort, OrchestratorPort)
│   └── schemas.py                    # Schémas de validation et sérialisation Pydantic v2
├── alembic/                          # Scripts de migration de base de données
├── tests/
│   ├── conftest.py                   # Fixtures de test & base SQLite mémoire
│   └── test_paas.py                  # Suite de tests d'intégration complète
├── scripts/
│   ├── demo.py                       # Démonstration automatisée du cycle de vie complet
│   ├── simulate_webhook.py           # Simulateur de webhooks multi-plateforme (Python)
│   └── simulate_webhook.sh           # Simulateur de webhooks pour terminaux Bash
├── Dockerfile                        # Image Docker de production optimisée
├── docker-compose.yml                # Composition conteneurisée (PostgreSQL 16 + API FastAPI)
├── .dockerignore                     # Exclusions pour la compilation d'image Docker
├── .gitignore                        # Fichiers ignorés par Git
├── requirements.txt                  # Dépendances Python
├── .env.example                      # Modèle de variables d'environnement
└── README.md                         # Documentation du projet
```

---

## 4. Machine à États du Projet

Chaque projet suit une machine à états stricte pour refléter son statut en temps réel :

```
[creating] ──> [awaiting_push] ──> [building] ──> [built] ──> [deploying] ──> [deployed]
     │                                │                             │
     └──> [failed]                    └──> [build_failed]           └──> [failed]
```

- **`creating`** : Enregistrement initial en base ; création du dépôt GitLab et configuration du webhook en cours.
- **`awaiting_push`** : Dépôt GitLab créé et vierge. En attente du premier commit/push de l'étudiant.
- **`building`** : Réception d'un webhook GitLab (`pending` ou `running`). La compilation de l'image est en cours.
- **`built`** : Le pipeline GitLab s'est terminé avec succès. L'image conteneur est publiée sur le Container Registry.
- **`deploying`** : Le backend a associé le SHA du commit au digest de l'image et a commandé le déploiement à l'Orchestrateur.
- **`deployed`** : L'Orchestrateur a instancié les pods Kubernetes et configuré l'Ingress. L'application est accessible en ligne.
- **États d'erreur** :
  - `build_failed` : Échec de la compilation dans GitLab CI (ex: erreur de Dockerfile ou tests unitaires échoués). Un nouveau `git push` relancera automatiquement le cycle.
  - `failed` : Erreur de communication infrastructure, image introuvable ou échec de déploiement Kubernetes. Le détail de l'erreur est consigné dans `project.error`.

---

## 5. Démarrage Rapide

### Option 1 : Avec Docker Compose (Recommandé)

Cette méthode lance l'environnement complet avec base de données **PostgreSQL 16** et l'API conteneurisée :

```bash
# 1. Démarrer les services en arrière-plan
docker compose up -d --build

# 2. Vérifier l'état des conteneurs
docker compose ps

# 3. Consulter les logs de l'API
docker compose logs -f api
```

L'API devient accessible sur :
- **Swagger UI** : [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc** : [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Vérification de santé** : [http://localhost:8000/health](http://localhost:8000/health)

Pour arrêter les conteneurs :
```bash
docker compose down
```

---

### Option 2 : Exécution Locale (Sans Docker)

```bash
# 1. Créer et activer l'environnement virtuel Python
python -m venv .venv
# Sur Windows :
.venv\Scripts\activate
# Sur Linux / macOS :
source .venv/bin/activate

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Créer le fichier .env à partir de l'exemple
cp .env.example .env

# 4. Appliquer les migrations de base de données
alembic upgrade head

# 5. Démarrer le serveur ASGI
uvicorn app.main:app --reload --port 8000
```

---

## 6. Guide de Test et de Validation

### Exécuter la Suite de Tests Automatisée
La suite de tests vérifie l'ensemble des règles métier, la sécurité d'accès multi-tenant, la déduplication des webhooks et les flux de déploiement :
```bash
pytest -v
```
*Résultat attendu : 11 tests passés avec succès.*

### Exécuter la Démo Complète de Bout en Bout
Avec l'API démarrée sur `http://localhost:8000` :
```bash
python scripts/demo.py
```
Ce script simule de manière autonome :
1. La création d'un projet par l'étudiante `alice` (`POST /projects`).
2. La détection du statut `awaiting_push`.
3. Le déclenchement du webhook GitLab CI de build (`building`).
4. La réussite du build et l'enregistrement de l'image (`built`).
5. La demande de déploiement auprès de l'Orchestrateur (`deploying`).
6. Le callback de confirmation Kubernetes avec génération de l'URL publique (`deployed`).
7. La consultation du statut final et des détails du projet.

### Simuler un Webhook Manuellement
Vous pouvez envoyer des événements de pipeline GitLab arbitraires pour tester la robustesse :
```bash
# Simuler un build en cours pour le projet 1
python scripts/simulate_webhook.py running 1

# Simuler un succès de build
python scripts/simulate_webhook.py success 1

# Simuler un échec de build
python scripts/simulate_webhook.py failed 1
```

---

## 7. Référentiel des Endpoints API

| Méthode | Route | En-tête d'Authentification | Description |
|---|---|---|---|
| `GET` | `/health` | *Aucun* | Vérification de santé du service et de la base de données |
| `POST` | `/projects` | `X-Dev-User: <username>` | Création d'un nouveau projet (statut initial `awaiting_push`) |
| `GET` | `/projects` | `X-Dev-User: <username>` | Liste des projets appartenant à l'utilisateur connecté |
| `GET` | `/projects/{id}` | `X-Dev-User: <username>` | Détail d'un projet (renvoie 404 si l'utilisateur n'en est pas propriétaire) |
| `GET` | `/projects/{id}/builds` | `X-Dev-User: <username>` | Liste des événements de pipeline du projet |
| `GET` | `/projects/{id}/images` | `X-Dev-User: <username>` | Liste des images conteneurs construites pour ce projet |
| `POST` | `/projects/{id}/deploy` | `X-Dev-User: <username>` | Déclenchement manuel d'un redéploiement ou rollback |
| `POST` | `/webhooks/gitlab` | `X-Gitlab-Token: <secret>` | Réception des notifications de pipeline GitLab CI (idempotent) |
| `POST` | `/internal/deployments/{id}/status` | `X-Internal-Token: <token>` | Callback sécurisé utilisé par l'Orchestrateur Kubernetes |

---

## 8. Guide pour Uploader le Projet sur GitHub

Pour publier ce projet sur votre propre compte GitHub :

1. **Créer un nouveau dépôt vierge sur GitHub** (par exemple nommé `paas-backend`) sans cocher l'initialisation de README ni de .gitignore.
2. **Ouvrir un terminal dans le dossier du projet** et exécuter les commandes suivantes :

```bash
# 1. Vérifier le statut des fichiers
git status

# 2. Ajouter tous les fichiers modifiés et nouvellement créés (.dockerignore, Dockerfile, etc.)
git add .

# 3. Enregistrer le commit
git commit -m "feat: complete dockerization and documentation for GANDAL PaaS backend"

# 4. Définir la branche principale sur main
git branch -M main

# 5. Relier à votre dépôt GitHub distant (remplacez VOTRE_UTILISATEUR par votre pseudo GitHub)
git remote add origin https://github.com/VOTRE_UTILISATEUR/paas-backend.git

# Si un remote origin existait déjà, mettez-le à jour :
# git remote set-url origin https://github.com/VOTRE_UTILISATEUR/paas-backend.git

# 6. Pousser le code vers GitHub
git push -u origin main
```

---

## 9. Passage en Production (Checklist Équipe)

Pour interconnecter le backend avec les vrais services de l'école :

1. **GitLab Réel** :
   - Définir `GITLAB_MODE=real` dans `.env`.
   - Renseigner `GITLAB_URL`, `GITLAB_TOKEN` (avec droits de création de projets et de webhooks dans le groupe), et `GITLAB_GROUP_ID`.
2. **Orchestrateur Kubernetes Réel** :
   - Définir `ORCHESTRATOR_MODE=real` dans `.env`.
   - Renseigner `ORCHESTRATOR_URL`.
   - Vérifier que l'Orchestrateur a accès au point d'entrée `/internal/deployments/{id}/status` avec la valeur configurée dans `INTERNAL_TOKEN`.
3. **Authentification OAuth** :
   - Définir `AUTH_MODE=oauth`.
   - Configurer l'application OAuth GitLab pour que le Portail Développeur transmette le jeton d'accès dans l'en-tête `Authorization: Bearer <token>`.
