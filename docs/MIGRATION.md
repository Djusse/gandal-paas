# Bascule et archivage (Phase 6)

Document opérationnel pour la fusion de `9ball9999/paas` et
`Djusse/gandal-paas` dans le monorepo `Djusse/gandal-paas`, branche
`integration` (décisions D1, D2, D7).

---

## 1. État de la fusion

| Étape | État | Détail |
|---|---|---|
| Phase 0 — Préparation | fait | Miroirs `merge/backup/*.git`, `gitleaks` sans résultat |
| Phase 1 — Historiques | fait | 26 commits, 3 auteurs, `git log -- backend/app/main.py` fonctionne |
| Phase 2 — Réorganisation | fait | `backend/`, `orchestrator/`, `infra/`, `deploy/`, `docs/` |
| Phase 3 — Orchestrateur | fait | Service HTTP, réconciliation, garde-fous, tests |
| Phase 4 — Intégration | fait | `deploy/docker-compose.yml`, `deploy/e2e.sh`, `deploy/test-postgres.sh` |
| Phase 5 — CI/CD | fait | `.github/workflows/ci.yml`, `LICENSE`, `CONTRIBUTING.md`, `CODEOWNERS` |
| Phase 6 — Bascule | **à faire** | PR `integration` → `main`, étiquette, archivage |

---

## 2. Vérifications avant d'ouvrir la PR

```bash
cd backend && pytest -q                 # 37 passed
cd ../orchestrator && pytest -q         # 58 passed
../.venv/bin/ruff check ...             # All checks passed
./deploy/test-postgres.sh               # 5 passed (R1)
```

Puis, avec un cluster :

```bash
./orchestrator/validation.sh alice memoire my-api   # 9/9, aucun ignoré
ORCHESTRATOR_MODE=real UP=1 ./deploy/e2e.sh         # HTTP 200
RESILIENCE=1 ORCHESTRATOR_MODE=real UP=1 ./deploy/e2e.sh
```

---

## 3. Ouvrir la pull request

```bash
git push -u origin integration

gh pr create \
  --base main \
  --head integration \
  --title "chore: fusion des dépôts paas et gandal-paas" \
  --body "Voir PLAN-FUSION-V2.md et docs/MIGRATION.md"
```

Revue attendue : les trois contributeurs (`fonkwa hermann`, `Delta Dev`,
`Cellule PaaS`).

Checklist de revue :

- [ ] `git shortlog -sn --no-merges` montre toujours les 3 auteurs ;
- [ ] `git log --follow -- backend/app/main.py` remonte l'historique d'origine ;
- [ ] aucun fichier supprimé hors des déplacements documentés ;
- [ ] `docs/contracts/` et les deux implémentations sont cohérents ;
- [ ] CI verte (backend, orchestrateur, scripts, anciens chemins, liens).

---

## 4. Étiqueter la version

```bash
git tag -a v0.1.0 -m "v0.1.0 — socle fusionné : API, orchestrateur, infra"
git push origin v0.1.0
```

---

## 5. Archiver l'ancien dépôt

Sur `9ball9999/paas`, remplacer le `README.md` par un renvoi, puis archiver :

```markdown
> **Dépôt archivé — fusionné dans Djusse/gandal-paas**
>
> Le code du backend vit désormais dans le monorepo :
> https://github.com/Djusse/gandal-paas/tree/main/backend
>
> L'historique d'origine a été conservé sous `backend/`
> (voir `docs/MIGRATION.md`). Ce dépôt reste en lecture seule.
```

```bash
gh repo archive 9ball9999/paas --yes
```

Ne pas supprimer le dépôt : les liens, les hashes et les références des
rapports LaTeX continueraient de pointer dans le vide (D7).

---

## 6. Mettre à jour les documents externes

| Document | Modification |
|---|---|
| `docs/simulation_v3.tex` | chemins `gandal_deploy.py` → `orchestrator/gandal_deploy.py` |
| `docs/explication_v3.tex` | mention de l'orchestrateur HTTP |
| `docs/diagrams/*.puml` | ajouter le service orchestrateur dans la vue globale |
| `docs/PRESENTATION.md` | remplacer la CLI par le service et `e2e.sh` |
| `docs/STATUS.md`, `NEXT_STEPS.md` | marquer comme historiques |

---

## 7. Ce qui change pour l'équipe

| Avant | Après |
|---|---|
| `python gandal_deploy.py deploy alice memoire my-api …` | `python orchestrator/gandal_deploy.py deploy alice memoire my-api …` (compatible) |
| namespace `project-{user}-{projet}` | namespace `proj-{projet}` |
| URL `{app}-{projet}-{user}.{domaine}` | URL `{projet}.{domaine}` |
| `~/tests/validation.sh` | `orchestrator/validation.sh` |
| scripts à la racine | `infra/aws/*.sh`, `infra/k3s/*.sh` |
| 1 réplica par défaut | 2 réplicas (D8) |

Les anciens noms de namespace ne sont plus produits : un projet créé avec
l'ancienne CLI doit être redéployé (`--purge` puis `deploy`) pour apparaître
sous `proj-{projet}`.

---

## 8. Retour arrière

- La fusion vit sur `integration` : `main` n'est pas modifiée avant la PR.
- Les miroirs d'origine sont dans `merge/backup/paas.git` et
  `merge/backup/gandal-paas.git` (clones `--mirror`), à conserver hors du dépôt.
- Si la bascule doit être annulée après fusion :
  `git revert -m 1 <sha-du-merge>` puis force-push interdit sur `main`
  (protection de branche) : passer par une PR de revert.
