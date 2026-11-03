# Plan de fusion — `9ball9999/paas` + `Djusse/gandal-paas`

*V2 — 3 novembre 2026. Établie d'après l'analyse du code et de l'historique des deux dépôts (état au dernier commit de `main`) et d'après les décisions D1 à D8 validées.*

## Changements de la V2

| Sujet | Changement | Où |
|---|---|---|
| Unicité des noms de projet | La contrainte (déjà présente dans le backend) est rendue explicite. `proj-{nom}` est conservé, faute de décision contraire ; l'alternative `proj-{id}` est documentée. | §2.1, §3 (D3), §6 |
| Fiabilité des déploiements | Pas de table de jobs ni d'outbox : l'état vit dans Kubernetes, avec boucle de réconciliation côté orchestrateur, relance périodique côté backend et `GET /deployments/{id}`. | R11, §3 (D9), Phase 3, §5 |
| Permissions et namespace | L'orchestrateur valide le namespace reçu ; permissions Kubernetes réduites. | R12, Phase 3 |
| CI/CD | Une CI minimale est avancée en Phase 2 ; la Phase 5 complète. | Phases 2 et 5 |
| Cohérence documentaire | Arborescence cible ajoutée (`deploy/`), archivage sans condition, accord de fusion et licence séparés (D6). | Phases 0, 2, 4, 6, §3 |
| **Non retenu** | Renforcement de la sécurité plus tôt (secrets par défaut, tokens ServiceAccount, registry…) : le durcissement reste au backlog, comme en V1. | Backlog |

---

## 0. En bref

Les deux dépôts **ne font pas double emploi, ils se complètent** :

| | `9ball9999/paas` | `Djusse/gandal-paas` |
|---|---|---|
| **Rôle** | **Plan de contrôle** : API FastAPI qui gère les projets, reçoit les webhooks GitLab, suit la machine à états, *demande* un déploiement | **Plan d'exécution** : K3s + registry privé + script qui *réalise* le déploiement (namespace, quotas, NetworkPolicy, Ingress) |
| **Ce qui manque** | Un vrai orchestrateur (seul un mock existe) | Une API pour piloter le script (il n'a qu'une CLI) |

Le backend attend déjà un orchestrateur qui expose `POST /deployments` et rappelle `POST /internal/deployments/{id}/status`. `gandal_deploy.py` fait exactement le travail Kubernetes que cet orchestrateur doit faire. **La fusion consiste donc à brancher les deux, en transformant `gandal_deploy.py` en service HTTP.**

**Recommandation :** un monorepo, historiques Git conservés, en 7 phases (§4). Il n'y a aucun conflit de fichiers (un dry-run a été fait, §8). Le vrai travail est la **réconciliation des conventions** (§2.1) et la **phase 3 (orchestrateur)**.

**Ce qu'il faut décider avant de commencer :** §3 (7 décisions, avec un choix par défaut pour chacune).

---

## 1. Analyse des deux projets

### 1.1 Vue comparative

| | `9ball9999/paas` | `Djusse/gandal-paas` |
|---|---|---|
| Fichiers / lignes | 40 / ~3 100 (dont `openapi.json` : 970) | 51 / ~10 600 (majorité : docs, LaTeX, PlantUML) |
| Historique | 3 commits (22–28 oct. 2026), 1 auteur (`fonkwa hermann`) | 22 commits (28–29 oct. 2026), 2 auteurs (`Delta Dev` ×15, `Cellule PaaS` ×7) |
| Langages | Python 3.12 | Bash, Python, PlantUML, LaTeX |
| Stack | FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, PostgreSQL 16 (SQLite en test) | K3s, Traefik, registry:2, client Python `kubernetes`, AWS CLI |
| Architecture | Hexagonale : `ports.py` + adaptateurs `fake/mock` ↔ `real` (variables `GITLAB_MODE`, `ORCHESTRATOR_MODE`, `AUTH_MODE`) | Script impératif idempotent (`upsert` create→patch sur 409) |
| Tests | 11 tests `pytest` — **11 passent** (vérifié) | 9 tests shell (`validation.sh`) exécutés sur AWS ; **non rejouables ici** |
| Conteneurisation | `Dockerfile` + `docker-compose.yml` (db + api) | Aucune (installation directe sur VM Ubuntu) |
| CI/CD | Aucune | Aucune |
| Licence | Aucune | Aucune |
| Packaging Python | `requirements.txt` (voir R6, §2.2) | Aucun : `pip install kubernetes` en dur dans `install.sh` |

### 1.2 Flux de bout en bout visé

```
Étudiant ─ POST /projects ─▶ backend ─▶ GitLab (dépôt + webhook)
   git push ─▶ GitLab CI (Kaniko) ─▶ image dans le registry
GitLab ─ webhook pipeline ─▶ backend ─ POST /deployments ─▶ ORCHESTRATEUR ─▶ K3s
backend ◀─ POST /internal/deployments/{id}/status (X-Internal-Token) ─ ORCHESTRATEUR
                                                       statut « deployed » + URL
```

Aujourd'hui, la case **ORCHESTRATEUR** n'existe qu'en deux moitiés : l'appelant (backend, `OrchestratorReal`) et le travail Kubernetes (`gandal_deploy.py`). Rien ne les relie.

### 1.3 Contrat d'interface existant côté backend (à implémenter côté orchestrateur)

| Sens | Appel | Contenu |
|---|---|---|
| backend → orch. | `POST {ORCHESTRATOR_URL}/deployments` | `{deployment_id, project, namespace, image, tag, digest, port, replicas}` → réponse `{deployment_ref}` |
| orch. → backend | `POST /internal/deployments/{id}/status` + en-tête `X-Internal-Token` | `{status: "deploying"\|"deployed"\|"failed", url, message}` |

Correspondance avec `gandal_deploy.py` : tout est présent (`namespace`, `image`, `port`, `replicas`), mais le script **recalcule** le namespace à partir de `user`/`project` au lieu de recevoir celui du backend, et il **ne renvoie aucun statut** (il s'arrête après la création des ressources).

---

## 2. Écarts et risques détectés

*Légende : ✅ constaté directement (exécution ou lecture explicite du code/des documents) · 📖 déduit du comportement attendu du code (à confirmer par un test).*

### 2.1 Conventions incompatibles à réconcilier

| Sujet | Backend | Infra | Impact |
|---|---|---|---|
| **Namespace** | `proj-{nom}` (calculé par le backend, transmis à l'orchestrateur) | `project-{user}-{project}` (recalculé par le script) | Deux namespaces différents pour la même appli |
| **Nom de projet** | `^[a-z][a-z0-9-]{2,29}$` (3–30 car.) | `^[a-z0-9]([-a-z0-9]*[a-z0-9])?$`, **20 car. max** | Un nom backend de 21–30 car. serait refusé par le script |
| **Tiret final** | ✅ accepté (`abc-` valide) | refusé | `proj-abc-` et `abc-.domaine` sont **invalides pour Kubernetes/DNS** : le backend peut accepter un nom que K3s refusera |
| **Identité** | `owner` = chaîne libre (en prod : nom d'utilisateur GitLab, qui peut contenir `.` `_`) | `user` ≤ 20 car., minuscules | Le nom d'utilisateur GitLab doit être normalisé avant d'être utilisé en label |
| **Modèle de données** | 1 projet = 1 appli = 1 dépôt | 1 user → N projets → N apps | Il faut fixer `gandal.io/app` (proposition : `app = nom du projet`) |
| **URL** | `http://{nom}.apps.gandal.local` (README) ; le mock renvoie `http://mock.gandal.local` | `{app}-{projet}-{user}.{GANDAL_BASE_DOMAIN}` | URL à unifier, et c'est l'orchestrateur qui la connaît |
| **Registry** | Registry GitLab (là où Kaniko pousse) | Registry privé K3s `localhost:5000`, HTTP, sans auth ; `registries.yaml` ne déclare **que** ce miroir | K3s ne saura pas tirer une image du registry GitLab sans configuration |
| **Image** | `repository` + `tag` + `digest` séparés | Une seule chaîne `image` | Le digest serait perdu : on déploierait un tag mutable |
| **Replicas** | 1 | 2 (défaut) | Choix produit à fixer |
| **Auth backend→orch.** | ✅ `OrchestratorReal` n'envoie **aucun en-tête d'authentification** | — | N'importe qui joignant le service pourrait déployer |

**Contrainte produit implicite : les noms de projet sont globalement uniques.** `Project.name` est `unique=True` et un doublon renvoie un 409 (✅ `test_case_2`). Deux étudiants ne peuvent donc pas avoir le même nom de projet, et `proj-{nom}` ne peut pas entrer en collision. Conséquences à assumer : premier arrivé, premier servi ; pas de renommage possible sans casser le namespace et l'URL. Si la règle change un jour (noms uniques par propriétaire), il faudra un identifiant numérique dans le namespace et l'URL (`proj-{id}`) : à décider **avant** l'ouverture à de vrais utilisateurs.

### 2.2 Bogues et risques

| # | Gravité | Constat | Où |
|---|---|---|---|
| R1 | **Élevée** 📖 | **Course entre déploiement et commit** : `on_build_success` appelle l'orchestrateur *avant* `db.commit()` (la ligne `Deployment` n'est qu'en `flush`). Avec un orchestrateur réel qui rappelle vite, le callback peut recevoir un **404** (ligne non visible sous PostgreSQL) ou voir son statut `deployed` **écrasé** par le commit tardif (`deploying`). `manual_deploy`, lui, commit avant d'appeler : les deux chemins sont incohérents. Invisible avec le mock (délai de 3 s) et SQLite en mémoire. | `backend/app/services/build_service.py` |
| R2 | Moyenne 📖 | `scripts/run-validation.sh` : heredoc **entre quotes** (`<< 'ENDSSH'`) → `${ELASTIC_IP}` n'est pas expansé et `GANDAL_BASE_DOMAIN` vaut `.sslip.io`. Il appelle aussi `~/tests/validation.sh` alors que ce script lance `gandal_deploy.py` en chemin relatif. Le même défaut a déjà été corrigé dans `deploy-alice.sh` (commits `12329e0`, `6a8f55f`) mais pas ici. | `scripts/run-validation.sh` |
| R3 | Moyenne ✅ | **Le test d'isolation réseau (test 3) a été ignoré** (« sonde indisponible »). Le rapport affiche « 9/9 » mais `validation.sh` compte 2 « OK » pour le test 7 : 9 OK = **8 tests distincts + 1 ignoré**. L'isolation n'a été validée que manuellement. | `VALIDATION_REPORT.md` |
| R4 | Moyenne ✅ | **Valeurs par défaut non sûres côté backend** : `WEBHOOK_SECRET` et `INTERNAL_TOKEN` = `change-me-long-random`, `AUTH_MODE=dev` (usurpation triviale via `X-Dev-User`), CORS `*` avec `allow_credentials=True`. | `backend/app/config.py`, `main.py` |
| R5 | Moyenne ✅ | **Registry exposé** : HTTP sans auth, `hostPort: 5000` sur le nœud. Acceptable en simulation, pas en production. | `registry.yaml`, `install.sh` |
| R6 | Faible ✅ | `requirements.txt` du backend est en **UTF-16 + CRLF** (pip l'accepte, vérifié, mais c'est fragile pour les outils et les diffs) et mélange dépendances d'exécution, `pytest` et paquets transitifs. | `requirements.txt` |
| R7 | Faible ✅ | **Valeurs d'infrastructure en dur** : IP `16.170.20.250`, ID d'instance, clé `~/gandal`. Région **incohérente** : `provision-aws.sh` → `eu-west-3`, `open-sg.sh` et `repair-access.sh` → `eu-north-1`. | `scripts/*.sh`, `STATUS.md` |
| R8 | Faible ✅ | **Documentation divergente** : `INDEX.md` cite des diagrammes inexistants (`architecture-globale.puml`…) alors que `diagrams/` contient `01…12-*.puml` ; `README.md` décrit une instance `t3.large` alors que le défaut est `m7i-flex.large` ; `STATUS.md`/`NEXT_STEPS.md` décrivent des phases « en cours » déjà validées. | docs infra |
| R9 | Info ✅ | **Aucune licence ni CI** dans les deux dépôts, et **deux propriétaires différents** : un accord explicite est nécessaire avant de republier le code ensemble. | — |
| R10 | Info ✅ | Balayage des deux historiques : **aucun secret réel** (seulement le placeholder `glpat-xxxx`). À refaire avec un outil dédié avant publication (Phase 0). | — |
| R11 | Moyenne 📖 | **Tâches en arrière-plan non durables** : `BackgroundTasks` (déjà utilisé par `on_build_success`) est perdu si le processus redémarre. Un orchestrateur construit de la même façon perdrait un déploiement accepté (202) mais non terminé. | `backend/app/routers/webhooks.py`, futur orchestrateur |
| R12 | Moyenne (conception) | **Namespace appliqué sans contrôle** : dans la version initiale de ce plan, l'orchestrateur appliquait le `namespace` reçu tel quel ; un jeton interne valide permettait de viser n'importe quel namespace (`kube-system`…). | Phase 3 |

### 2.3 Dépendances externes hors périmètre

Le pipeline `templates/build.yml@paas/ci-templates` (Kaniko) et l'instance GitLab ne sont dans **aucun** des deux dépôts. Le plan les traite comme des dépendances : en simulation, on garde `GitLabFake`.

### 2.4 Limites de cette analyse

Dépôts lus en **lecture seule** (rien n'a été poussé). Les scripts AWS/K3s n'ont pas pu être exécutés ici : leur comportement s'appuie sur `VALIDATION_REPORT.md`. Les points 📖 sont des déductions du code, pas des défaillances observées.

---

## 3. Décisions à valider avant de commencer

| # | Décision | Choix recommandé | Alternative |
|---|---|---|---|
| D1 | **Dépôt cible** | `Djusse/gandal-paas` (historique le plus riche, nom du projet), via une branche `integration` — **sans toucher à `main` avant la revue** | Nouveau dépôt d'organisation |
| D2 | **Structure** | **Monorepo** : `backend/`, `orchestrator/`, `infra/`, `docs/` | Deux dépôts liés par sous-module Git (plus lourd, le contrat backend↔orchestrateur évolue ensemble) |
| D3 | **Qui possède la convention de nommage ?** | **Le backend.** Il transmet `namespace` (`proj-{nom}`), le `owner` et le `name` ; l'orchestrateur les applique sans recalculer. Labels : `gandal.io/owner={owner normalisé}`, `gandal.io/project={nom}`, `gandal.io/app={nom}`. URL : `{nom}.{GANDAL_BASE_DOMAIN}` (`<IP>.sslip.io` sur AWS, `apps.gandal.local` en prod). Les noms de projet restent **globalement uniques** (§2.1). | Adopter `project-{user}-{project}` : casse avec les noms d'utilisateur GitLab (§2.1) |
| D4 | **Forme de l'orchestrateur** | **Service HTTP dans le cluster** (FastAPI + `load_incluster_config`, ServiceAccount/RBAC dédiés) | Importer `gandal_deploy.py` dans le backend : couple le backend à Kubernetes et casse l'architecture hexagonale |
| D5 | **Registry** | Simulation AWS : registry K3s `localhost:5000`. Cible : **registry GitLab** + `imagePullSecret`/`registries.yaml`. Le code accepte les deux. | — |
| D6 | **Licence et droits** | Obtenir l'accord écrit des 3 contributeurs (`fonkwa hermann`, `Delta Dev`, `Cellule PaaS`), puis choisir une licence | — |
| D7 | **Sort des anciens dépôts** | Les **archiver** avec un README renvoyant vers le nouveau dépôt, après la bascule | Les supprimer (déconseillé : liens et hashes cassés) |

### Décisions validées (3 novembre 2026)

| # | Décision retenue |
|---|---|
| D1 | Dépôt cible : **`Djusse/gandal-paas`**, branche `integration` |
| D2 | **Monorepo** (`backend/`, `orchestrator/`, `infra/`, `docs/`) |
| D3 | **Convention du backend** : namespace `proj-{nom}`, URL `{nom}.{GANDAL_BASE_DOMAIN}`, propriétaire en label |
| D4 | **Service HTTP dans K3s** |
| D5 | **Registry K3s d'abord** (`localhost:5000`, `GitLabFake`) ; registry GitLab dans une phase ultérieure |
| D6 | Accord de **fusion** déclaré par les contributeurs (à conserver par écrit, Phase 0). **Licence** à choisir en Phase 5, avec l'accord écrit des titulaires des droits, à identifier en Phase 0. |
| D7 | Anciens dépôts **archivés avec un README de renvoi** |
| D8 | **2 réplicas par défaut** (le backend, qui envoie 1 aujourd'hui, est aligné sur l'infra ; quota de 4 pods par projet inchangé) |
| D9 | *(retenue en V2, issue de la revue)* **Fiabilité sans file de jobs** : état conservé dans Kubernetes, boucle de réconciliation côté orchestrateur, relance périodique côté backend (Phase 3). Une outbox transactionnelle reste une évolution possible. |

---

## 4. Plan d'exécution

*Effort relatif : **S** = petit, **M** = moyen, **L** = important.*

### Phase 0 — Préparation (S)

- [x] Décisions D1 à D8 validées (§3) ; D9 retenue en V2.
- [ ] Geler les deux dépôts (annoncer « plus de push sur `main` »).
- [ ] Sauvegarde : `git clone --mirror` des deux dépôts.
- [ ] Balayage de secrets sur les deux historiques avec un outil dédié (`gitleaks` ou `trufflehog`).
- [ ] Installer `git-filter-repo` (`pip install git-filter-repo`).
- [ ] Droits : identifier les titulaires des droits de chaque dépôt et conserver par écrit leur accord de **fusion** (l'accord sur la **licence** est traité en Phase 5).

**Sortie :** décisions écrites, sauvegardes faites, aucun secret détecté, accords de fusion conservés.

### Phase 1 — Fusion des historiques (S)

On réécrit **uniquement** l'historique du backend (3 commits, ses hashes changeront) pour que `git log`/`git blame` fonctionnent fichier par fichier sous `backend/`. L'historique infra reste intact.

```bash
mkdir ~/merge && cd ~/merge

# 1. Backend : réécriture de l'historique sous backend/
git clone https://github.com/9ball9999/paas.git backend-src
git -C backend-src filter-repo --to-subdirectory-filter backend

# 2. Cible : clone de Djusse/gandal-paas (historique inchangé)
git clone https://github.com/Djusse/gandal-paas.git gandal-paas
cd gandal-paas
git checkout -b integration

# 3. Fusion des historiques sans lien
git remote add backend-src ../backend-src
git fetch backend-src
git merge --allow-unrelated-histories backend-src/main \
    -m "chore: merge 9ball9999/paas history into backend/"

# 4. Contrôles
git shortlog -sn --no-merges        # 3 auteurs attendus
git log --oneline -- backend/app/main.py
(cd backend && pytest -q)           # 11 passed
```

**Sortie :** branche `integration` avec les 25 commits d'origine + 1 commit de fusion, les 3 auteurs, et 11 tests verts depuis `backend/`.

### Phase 2 — Réorganisation du dépôt (S–M)

Déplacements avec `git mv` (l'historique reste suivi par `git log --follow`), en un commit dédié :

| Ancien emplacement (racine infra) | Nouvel emplacement |
|---|---|
| `gandal_deploy.py` | `orchestrator/gandal_deploy.py` |
| `tests/validation.sh` | `orchestrator/validation.sh` |
| `install.sh`, `registry.yaml` | `infra/k3s/` |
| `scripts/provision-aws.sh`, `open-sg.sh`, `add-pc-key.sh`, `repair-access.sh`, `ssh-kubectl.sh`, `deploy-alice.sh`, `run-validation.sh`, `deploy-demo.sh` | `infra/aws/` |
| `ARCHITECTURE.md`, `PRESENTATION.md`, `INDEX.md`, `VALIDATION_REPORT.md`, `STATUS.md`, `NEXT_STEPS.md`, `DEMO_LANDING_PAGE.md`, `diagrams/`, `*.tex` | `docs/` |
| `README.md` (infra) | `docs/README-infra.md` |
| `demo/` | `demo/` (inchangé) |

**Arborescence cible**

```text
gandal-paas/
├── backend/          # API FastAPI (ex 9ball9999/paas) ; son docker-compose.yml reste local au backend
├── orchestrator/     # service HTTP + module Kubernetes (ex gandal_deploy.py) + validation.sh
├── infra/
│   ├── k3s/          # install.sh, registry.yaml, manifestes (orchestrator.yaml, RBAC)
│   └── aws/          # scripts de provisionnement et de démonstration
├── deploy/           # (créé en Phase 4) docker-compose.yml d'intégration + e2e.sh
├── docs/             # architecture, diagrammes, rapports, contrats (docs/contracts/)
├── demo/
├── .github/workflows/
└── README.md
```

- [ ] Réécrire les chemins relatifs cassés par les déplacements : `deploy-demo.sh` (`$HOME/gandal-paas/gandal_deploy.py`, `../demo`), `run-validation.sh` (`~/tests/validation.sh`), `validation.sh` (`gandal_deploy.py` relatif), liens de `INDEX.md`.
- [ ] Corriger R2 (heredoc non expansé) et R8 (docs divergentes).
- [ ] Fusionner les `.gitignore` (union : Python, `.env`, `*.db`, LaTeX, `kubeconfig`, `.kube/`).
- [ ] Convertir `backend/requirements.txt` en UTF-8/LF ; séparer `requirements.txt` (exécution) et `requirements-dev.txt` (`pytest`).
- [ ] Remplacer les valeurs en dur (R7) par des variables (`ELASTIC_IP`, `AWS_REGION`, `KEY_PATH`) et **unifier la région**.
- [ ] Nouveau `README.md` racine : vue d'ensemble, schéma du §1.2, démarrage rapide, liens vers `backend/`, `orchestrator/`, `infra/`, `docs/`.
- [ ] **CI minimale** (`.github/workflows/ci.yml`), dès maintenant car cette phase déplace chemins, scripts et dépendances : `pytest` du backend, `ruff`, `shellcheck` sur tous les scripts, `python -m py_compile`, et un contrôle qu'aucun ancien chemin ne subsiste (`gandal_deploy.py` à la racine, `~/tests/`…).

**Sortie :** arborescence cible en place, `pytest` vert depuis `backend/`, plus aucun chemin cassé (vérifié par la CI minimale), CI verte sur `integration`.

### Phase 3 — Orchestrateur : le travail d'intégration (L)

**3.1 Refactorer `gandal_deploy.py`** en module réutilisable (`orchestrator/gandal/k8s.py`) dont les fonctions reçoivent explicitement `namespace`, `labels`, `host`, `image`, `port`, `replicas` (plus de calcul interne). La CLI devient une fine couche au-dessus (compatibilité avec `validation.sh`). Validation des noms alignée sur DNS-1123 (≤ 63), pas sur « 20 caractères » (D3).

**3.2 Service HTTP** (`orchestrator/app/`) :

- `POST /deployments` : valide la requête (voir « Garde-fous » plus bas), **applique les ressources Kubernetes avant de répondre** `202 {deployment_ref}`, et inscrit le `deployment_id` en annotation du `Deployment` (`gandal.io/deployment-id`). Rejouer le même `deployment_id` met à jour sans créer de doublon.
- **L'état vit dans Kubernetes, pas dans une file de jobs** (R11) : un redémarrage de l'orchestrateur ne perd donc aucun déploiement accepté. Une **boucle de réconciliation** (au démarrage, puis toutes les ~30 s) parcourt les `Deployment` gérés (label `gandal.io/managed=true`). Quand le rollout est terminé ou a dépassé son délai et que l'annotation `gandal.io/reported-status` diffère, elle envoie `deployed` (+ `url`) ou `failed` (+ `message`) à `POST {BACKEND_URL}/internal/deployments/{id}/status` (`X-Internal-Token`), avec retries et attente croissante, puis met l'annotation à jour. L'envoi de `deploying` est optionnel.
- `GET /deployments/{deployment_id}` : renvoie l'état courant lu dans Kubernetes, pour que le backend puisse l'interroger si un rappel s'est perdu.
- Image déployée : `repository@digest` si le digest est connu, sinon `repository:tag`.
- Authentification entrante par jeton partagé (en-tête dédié) ; `GET /health`.
- Exécution dans le cluster : `load_incluster_config()`, ServiceAccount dédié. **Permissions minimales** : un `ClusterRole` limité aux `namespaces` (créer, lire, modifier, supprimer) et, pour les ressources applicatives (resourcequotas, limitranges, networkpolicies, deployments, services, ingresses), des droits accordés **par namespace** (un `RoleBinding` créé avec le namespace, ce qui exige le droit `bind` sur le rôle concerné). Si cette variante s'avère trop lourde sur K3s, repli documenté vers un `ClusterRole` unique, **protégé par les garde-fous ci-dessous**. Manifestes dans `infra/k3s/orchestrator.yaml`.
- **Garde-fous (R12)** : un jeton interne valide ne vaut pas autorisation sur n'importe quel namespace. L'orchestrateur refuse toute requête dont `namespace` ≠ `proj-{project}`, refuse les namespaces réservés (`kube-system`, `kube-public`, `kube-node-lease`, `default`, `gandal-system`), et ne modifie que des namespaces portant `gandal.io/managed=true` (label posé par lui à la création).

**3.3 Changements côté backend (petits mais obligatoires)** :

- [ ] **Corriger R1** : committer la ligne `Deployment` (statut `requested`) *avant* d'appeler l'orchestrateur, comme le fait déjà `manual_deploy` ; rendre le callback `/internal/...` monotone (ne jamais faire repasser `deployed` à `deploying`).
- [ ] **Relance périodique (R1, R11)** : tâche asynchrone démarrée au lancement du backend, toutes les ~60 s. Un `Deployment` resté `requested` au-delà d'un délai est renvoyé à l'orchestrateur (sans danger : l'appel est idempotent). Un `Deployment` resté `deploying` est interrogé par `GET /deployments/{id}` et son statut est rattrapé. Cela couvre le cas « commit réussi mais requête HTTP jamais envoyée » sans table d'événements ; une outbox transactionnelle reste possible plus tard si le volume l'exige.
- [ ] `OrchestratorReal` : envoyer le jeton d'authentification, ajouter retries et timeout configurable (nouvelle variable `ORCHESTRATOR_TOKEN`).
- [ ] Resserrer la regex de nom : `^[a-z][a-z0-9-]{1,28}[a-z0-9]$` (plus de tiret final, §2.1).
- [ ] Envoyer `owner` dans la requête de déploiement (pour les labels).
- [ ] Passer le nombre de réplicas par défaut de 1 à 2 (D8), aux deux endroits où il est écrit en dur (`build_service.py` et `project_service.py`).
- [ ] Optionnel : `DELETE /projects/{id}` → purge du namespace (le backend n'a aucune route de suppression alors que `--purge` existe côté infra).

**3.4 Tests**

- [ ] Tests unitaires de l'orchestrateur avec un client Kubernetes simulé (idempotence, 409→patch, validation des noms).
- [ ] **Tests de contrat** : un schéma JSON partagé (`docs/contracts/`) vérifié des deux côtés, pour que backend et orchestrateur ne dérivent pas.
- [ ] Test d'intégration du backend sur **PostgreSQL** (compose) qui rejoue la course R1.
- [ ] Rendre le test 3 de `validation.sh` fiable (attendre la présence de l'image de sonde) pour obtenir une vraie preuve d'isolation (R3).
- [ ] Tests de fiabilité : redémarrage de l'orchestrateur pendant un déploiement (le projet atteint tout de même `deployed`) ; rappel échoué puis rejoué ; `Deployment` bloqué rattrapé par la relance du backend (sans doublon).
- [ ] Tests des garde-fous : sont refusés un namespace `kube-system`, un namespace ≠ `proj-{project}` et un namespace sans label `gandal.io/managed`.

**Sortie :** le backend en `ORCHESTRATOR_MODE=real` déploie une image sur K3s et reçoit `deployed` + URL, sans modifier la logique métier hors R1, y compris si l'orchestrateur redémarre en cours de route.

### Phase 4 — Environnement intégré et test de bout en bout (M)

- [ ] `deploy/docker-compose.yml` (le dossier `deploy/` est créé à cette phase, voir l'arborescence de la Phase 2) : db + backend (+ orchestrateur pointé sur un cluster `k3d` local pour le développement).
- [ ] Sur AWS : `GITLAB_MODE=fake`, `ORCHESTRATOR_MODE=real`, orchestrateur dans K3s, registry `localhost:5000`. Le `GitLabFake` renvoie des images pointant vers ce registry.
- [ ] Script `deploy/e2e.sh` : `POST /projects` → image de test poussée → `simulate_webhook.py success` → attente de `deployed` → `curl` de l'URL = **HTTP 200** → suppression.
- [ ] Scénario de résilience dans `e2e.sh` : redémarrer le pod de l'orchestrateur pendant un déploiement ; le projet doit quand même atteindre `deployed`.
- [ ] Rejouer les 9 tests de `validation.sh` **et** la suite `pytest` ; réconcilier les deux rapports en un seul.

**Sortie :** `e2e.sh` vert sur AWS et en local ; rapport de validation unique, avec le test d'isolation réellement exécuté.

### Phase 5 — CI/CD et hygiène (M)

- [ ] Compléter la CI (la CI minimale existe depuis la Phase 2) : tests de l'orchestrateur, build Docker des deux images, tests d'intégration sur PostgreSQL, vérification des liens Markdown.
- [ ] Protection de la branche `main`, revue obligatoire, `pre-commit`, Dependabot, analyse de secrets en CI.
- [ ] `LICENSE` (D6), `CONTRIBUTING.md`, `CODEOWNERS` (une zone par équipe : backend / infra).

**Sortie :** une PR ne peut être fusionnée que si la CI est verte.

### Phase 6 — Bascule et archivage (S)

- [ ] Ouvrir la PR `integration` → `main`, revue par les 3 contributeurs.
- [ ] Étiqueter `v0.1.0` après fusion.
- [ ] Archiver `9ball9999/paas` avec un README de redirection vers `Djusse/gandal-paas`, qui devient le dépôt principal (D1, D7).
- [ ] Mettre à jour les liens externes (rapports, présentation) et prévenir l'équipe.

### Backlog après fusion (hors périmètre immédiat)

Durcissement pour la production (R4/R5) : refus de démarrer avec les secrets par défaut, `AUTH_MODE=oauth`, CORS restreint, TLS (cert-manager), registry avec TLS + authentification, NetworkPolicies d'*egress*, `securityContext` (non-root, système de fichiers en lecture seule), observabilité ; portage des scripts AWS vers XCP-ng ; intégration du vrai GitLab + Kaniko.

---

## 5. Contrat cible backend ↔ orchestrateur (proposition)

**`POST /deployments`** (en-tête d'authentification dédié)

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
→ `202 {"deployment_ref": "orch-42"}`, renvoyé **une fois les ressources appliquées** (rejouer le même `deployment_id` ne crée pas de doublon).
Règle : `namespace` doit valoir `proj-{project}` et ne pas être un namespace réservé, sinon `422`.

**`GET /deployments/42`** → `{"status": "deploying|deployed|failed", "url": "…", "message": "…"}` : état lu dans Kubernetes, utilisé par le backend comme repli quand un rappel s'est perdu.

**`POST {BACKEND_URL}/internal/deployments/42/status`** (en-tête `X-Internal-Token`)

```json
{ "status": "deployed", "url": "http://mon-app.16.x.x.x.sslip.io", "message": "" }
```
`status` ∈ `deploying | deployed | failed` (inchangé côté backend : `owner` est le seul champ ajouté à la requête).

---

## 6. Risques de la fusion elle-même

| Risque | Probabilité | Mitigation |
|---|---|---|
| Hashes du backend modifiés par `filter-repo` | Certaine (3 commits) | Acceptable ; archiver l'ancien dépôt plutôt que le supprimer |
| Perte de suivi des fichiers déplacés | Faible | `git mv` en un commit dédié, sans modification de contenu |
| Chemins cassés après réorganisation | Élevée | CI minimale dès la Phase 2 (`shellcheck`, recherche des anciens chemins), puis `deploy/e2e.sh` en Phase 4 |
| Course R1 non reproduite en test | Moyenne | Test d'intégration sur PostgreSQL, pas SQLite |
| Désaccord sur la convention de nommage | Moyenne | Trancher D3 en Phase 0 ; sinon l'orchestrateur reste figé |
| Écrasement de `main` par erreur | Faible | Travail sur `integration`, protection de branche (Phase 5) |
| Coûts AWS pendant les tests | Moyenne | Instance éteinte entre sessions ; `provision-aws.sh down` en fin de phase 4 (~0,10 $/h d'après le rapport) |
| Double envoi lors de la relance du backend | Moyenne | Appels idempotents sur `deployment_id` ; test dédié (Phase 3.4) |
| Boucle de réconciliation de l'orchestrateur trop agressive ou muette | Faible | Intervalle configurable, journalisation de chaque rappel, test de redémarrage en E2E |
| Droits RBAC par namespace trop lourds à mettre en place sur K3s | Moyenne | Repli documenté vers un `ClusterRole` unique, protégé par les garde-fous R12 |
| Règle d'unicité des noms remise en cause plus tard | Faible | Documentée en §2.1 ; migration vers `proj-{id}` à prévoir avant l'ouverture aux utilisateurs |

---

## 7. Critères d'acceptation

- [ ] Un seul dépôt, 3 auteurs et 25 commits d'origine préservés, `git log` par fichier fonctionnel.
- [ ] `pytest` vert (backend et orchestrateur), `shellcheck` sans erreur.
- [ ] `ORCHESTRATOR_MODE=real` : de `POST /projects` à une URL répondant **200**, via `deploy/e2e.sh`.
- [ ] Redémarrer l'orchestrateur en plein déploiement n'empêche pas le projet d'atteindre `deployed` (scénario de résilience de `e2e.sh`).
- [ ] L'orchestrateur refuse un namespace réservé ou différent de `proj-{project}` (test automatique).
- [ ] Test d'isolation réseau **exécuté et réussi** (plus « ignoré »).
- [ ] Risque R1 corrigé et couvert par un test PostgreSQL.
- [ ] Aucun secret ni identifiant d'infrastructure en dur ; région AWS unique.
- [ ] CI minimale active dès la Phase 2 ; CI complète verte, `main` protégée, licence en place.
- [ ] `INDEX.md` et les README décrivent l'arborescence réelle.

---

## 8. Vérifications déjà réalisées pour ce plan

| Vérification | Résultat |
|---|---|
| Suite `pytest` du backend, dans un environnement vierge | **11 passés** |
| Syntaxe de `gandal_deploy.py`, `install.sh`, 9 scripts Bash | OK |
| Installation du `requirements.txt` UTF-16 avec `pip` | OK |
| Unicité du nom de projet dans le backend | `unique=True` + 409 sur doublon, couvert par `test_case_2` (qui passe) |
| **Dry-run de fusion** avec `git-filter-repo` (copies jetables, dépôts d'origine intacts) | 26 commits, 3 auteurs conservés, `git log`/`blame` par fichier OK, **11 tests verts depuis `backend/`** |
| Dry-run de la réorganisation par `git mv` | Aucune collision de fichier ; l'arborescence cible se construit sans conflit |
| Balayage de secrets dans les deux historiques | Aucun secret réel |

**Non vérifié (hors de portée ici) :** build Docker, exécution sur AWS/K3s, comportement avec un vrai GitLab, test d'intégration sur PostgreSQL (R1).
