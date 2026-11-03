# Contribuer à GANDAL PaaS

## Avant de commencer

- Lire [`README.md`](README.md) et [`docs/INDEX.md`](docs/INDEX.md).
- Le plan de fusion ([`PLAN-FUSION-V2.md`](docs/PLAN-FUSION-V2.md)) documente les décisions
  D1–D9 : elles ne se rediscutent pas dans une PR, mais dans une issue.
- Les noms de projet sont **globalement uniques** et le namespace est
  `proj-{nom}`. Un changement sur cette convention est un changement de
  contrat (D3) : il touche le backend, l'orchestrateur et les tests de contrat.

## Mise en place

```bash
git clone https://github.com/Djusse/gandal-paas.git
cd gandal-paas

python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt
pip install -r orchestrator/requirements-dev.txt
```

## Règles de développement

| Zone | Dossier | Tests | Responsable |
|---|---|---|---|
| Backend | [`backend/`](backend/) | `cd backend && pytest -q` | équipe backend |
| Orchestrateur | [`orchestrator/`](orchestrator/) | `cd orchestrator && pytest -q` | équipe infra |
| Infrastructure | [`infra/`](infra/) | `shellcheck` | équipe infra |
| Contrats | [`docs/contracts/`](docs/contracts/) | `orchestrator/tests/test_contracts.py` | les deux |

- **Contrat d'abord.** Toute évolution du corps de `POST /deployments` ou du
  rappel de statut commence par les schémas de `docs/contracts/` et leurs tests.
- **Pas de secret** dans le dépôt : utiliser `.env` (ignoré) et
  `*.example`. La CI analyse les secrets.
- **Idempotence** : tout appel de déploiement doit pouvoir être rejoué sans
  créer de ressource en double (`deployment_id` est la clé).
- **Garde-fous R12** : l'orchestrateur ne touche jamais un namespace réservé ni
  un namespace sans le label `gandal.io/managed=true`.

## Avant d'ouvrir une PR

```bash
# Style et tests
ruff check backend/app backend/tests
ruff check orchestrator/gandal orchestrator/app orchestrator/tests
pytest -q                      # depuis backend/ puis orchestrator/
shellcheck -S warning infra/k3s/*.sh infra/aws/*.sh orchestrator/validation.sh deploy/*.sh
```

La PR doit :

1. décrire le comportement avant/après ;
2. référencer l'issue ou la décision du plan concernée ;
3. indiquer les tests ajoutés (nom du fichier et cas couvert) ;
4. rester limitée à une zone (backend, orchestrateur, infra, docs) si possible.

## Commits

Convention : `type(zone): résumé` (`feat`, `fix`, `refactor`, `test`, `docs`,
`chore`, `ci`). Exemples :

```text
fix(backend): committer le déploiement avant l'appel à l'orchestrateur
feat(orchestrator): ajouter GET /deployments/{id}
test(orchestrator): couvrir le refus des namespaces réservés
```

## Revue

- Une revue par zone est requise (voir [`CODEOWNERS`](.github/CODEOWNERS)).
- `main` est protégée : CI verte, une approbation, pas de force-push.
- Les branches de travail sont fusionnées dans `integration` avant `main`
  pendant la période de bascule.

## Licence

En contribuant, vous acceptez que votre contribution soit publiée sous la
licence MIT du dépôt (voir [`LICENSE`](LICENSE)).
