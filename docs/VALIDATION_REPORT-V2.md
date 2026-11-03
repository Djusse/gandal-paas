# Rapport de validation — après fusion (V2)

**Date :** 3 novembre 2026
**Périmètre :** monorepo `gandal-paas` (backend + orchestrateur + infra)
**Référence :** [`PLAN-FUSION-V2.md`](PLAN-FUSION-V2.md)

Ce rapport remplace le rapport historique [`VALIDATION_REPORT.md`](VALIDATION_REPORT.md)
pour la phase d'intégration. Il distingue explicitement ce qui a été **exécuté
ici** de ce qui **reste à exécuter sur un cluster**.

---

## 1. Ce qui a été vérifié localement

| Vérification | Commande | Résultat |
|---|---|---|
| Tests backend | `cd backend && pytest -q` | **37 passed** |
| Tests orchestrateur | `cd orchestrator && pytest -q` | **58 passed** |
| Contrats JSON ↔ modèles | inclus dans `orchestrator/tests/test_contracts.py` | **8 passed** |
| Ruff backend | `ruff check backend/app backend/tests` | **All checks passed** |
| Ruff orchestrateur | `ruff check orchestrator/gandal orchestrator/app orchestrator/tests` | **All checks passed** |
| Compilation | `python -m compileall gandal app gandal_deploy.py` | OK |
| Fusion des historiques | `git shortlog -sn --no-merges` | **26 commits, 3 auteurs** |
| Balayage de secrets | `gitleaks git` sur les deux miroirs | **aucune fuite** |
| Manifestes YAML | parsing PyYAML | OK |
| Liens Markdown internes | contrôle CI | OK |
| **Tests PostgreSQL (R1)** | `deploy/test-postgres.sh` | **5 passed** (PostgreSQL 9.6 local) |

### Détail des tests backend (37)

| Fichier | Cas couverts |
|---|---|
| `tests/test_paas.py` (11) | Création, doublon 409, isolation utilisateur, webhook, idempotence, rollback GitLab, callback interne |
| `tests/test_deployment_flow.py` (26) | Monotonie `deployed`/`failed`, **R1** (commit avant appel), contrat de requête, relance `requested` et `deploying`, regex sans tiret final, suppression, historique |

### Détail des tests orchestrateur (58)

| Fichier | Cas couverts |
|---|---|
| `tests/test_k8s.py` | Application des 6 ressources, **idempotence** (409 → patch), préférence du digest, labels normalisés, garde-fous namespace, port/réplicas, état `deploying`/`deployed`/`failed`, suppression protégée |
| `tests/test_api.py` | Jeton obligatoire, `202` + `deployment_ref`, idempotence HTTP, refus `kube-system` / namespace incohérent, `GET` d'état, `DELETE`, réconciliation (succès, échec, retry, non géré), notifier (jeton, payload, erreur) |
| `tests/test_contracts.py` | Schémas valides, requête acceptée/refusée, réponses alignées sur les modèles |

---

## 2. Ce qui reste à exécuter sur un cluster

| Vérification | Où | Critère |
|---|---|---|
| `orchestrator/validation.sh` (9 tests) | VM K3s + registry | 9/9 **sans aucun test ignoré** |
| Test d'isolation réseau réel | VM K3s | Bob `000`, Alice `200` (image `curl` publiée) |
| `deploy/e2e.sh` | AWS ou local + k3d | `deployed` puis HTTP **200** |
| Scénario de résilience | `RESILIENCE=1 deploy/e2e.sh` | `deployed` malgré redémarrage de l'orchestrateur |
| Build des images | Docker | `backend` et `orchestrator` |

### Test PostgreSQL exécuté

Les 5 tests d'intégration ont été exécutés sur un PostgreSQL réel
(`postgres:9.6-alpine`, faute de pouvoir télécharger 16-alpine) :

| Test | Ce qui est prouvé |
|---|---|
| `test_database_is_postgresql` | La cible est bien PostgreSQL |
| `test_row_visible_from_another_connection_after_commit` | La ligne `Deployment` est visible d'une autre transaction après commit (**R1 corrigé**) |
| `test_uncommitted_row_is_invisible` | Contre-preuve : un simple `flush` la rend invisible (le défaut R1 d'origine) |
| `test_callback_does_not_overwrite_deployed` | Un statut terminal n'est jamais écrasé |
| `test_duplicate_project_name_rejected_by_database` | L'unicité du nom est garantie par la base |

Résultat : **5 passed**. Le script `deploy/test-postgres.sh` cible
`postgres:16-alpine` en CI.

---

## 3. Corrections livrées dans cette phase

| Réf. | Correction | Emplacement | Test |
|---|---|---|---|
| **R1** | Commit avant l'appel à l'orchestrateur ; callback monotone | `backend/app/services/deployment_service.py`, `routers/internal.py` | `test_build_success_commits_before_calling_orchestrator`, `test_callback_does_not_overwrite_deployed` |
| **R2** | Heredoc expansé, chemins corrigés | `infra/aws/run-validation.sh` | `shellcheck` + CI « anciens chemins » |
| **R3** | Test d'isolation : échec explicite si la sonde manque | `orchestrator/validation.sh` | Revue de code + exécution cluster |
| **R6** | `requirements.txt` UTF-8/LF, séparation dev | `backend/requirements*.txt` | Étape CI « format des requirements » |
| **R7** | IP/région/clé en variables, région unifiée `eu-west-3` | `infra/aws/*.sh` | `shellcheck` |
| **R8** | `INDEX.md` réécrit sur l'arborescence réelle | `docs/INDEX.md` | CI « liens Markdown » |
| **R11** | État dans Kubernetes + relance périodique backend | `orchestrator/gandal/service.py`, `backend/app/services/deployment_service.py` | `test_recovery_*` |
| **R12** | Namespace validé, réservé refusé, label `managed` exigé | `orchestrator/gandal/names.py`, `k8s.py` | `test_reserved_namespace_refused`, `test_namespace_must_match_project`, `test_delete_requires_managed_label` |
| **D3** | Namespace `proj-{nom}`, URL `{nom}.{domaine}` | backend + orchestrateur | `test_case_1`, `test_deploy_accepts_valid_request` |
| **D8** | 2 réplicas par défaut | `config.py` des deux services | `test_deploy_request_contract` |

---

## 4. Limites connues

- Le `GitLabFake` renvoie un digest factice : le déploiement réel dépend du
  registry et de la présence de l'image sur le nœud.
- Les tests d'intégration PostgreSQL sont conditionnés à `PG_TEST_URL` ; ils
  sont ignorés (et signalés comme tels) en son absence.
- Les scripts AWS/K3s n'ont pas été exécutés ici : leur validation s'appuie sur
  `shellcheck`, la syntaxe Bash et la revue.

---

## 5. Conclusion

Le contrat backend ↔ orchestrateur est implémenté, testé et vérifié des deux
côtés par des schémas partagés. Les corrections R1 et R12 sont couvertes par
des tests automatiques. La validation sur cluster (`validation.sh`, `e2e.sh`)
reste la dernière étape avant la bascule vers `main`.
