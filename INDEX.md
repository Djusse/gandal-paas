# 📚 Index de la documentation GANDAL PaaS

Bienvenue dans le projet GANDAL PaaS ! Ce fichier te guide vers tous les documents disponibles.

---

## 🚀 Démarrage rapide

Tu veux comprendre le projet rapidement ? Commence par :

1. **[README.md](README.md)** - Vue d'ensemble et guide d'installation
2. **[ARCHITECTURE.md](ARCHITECTURE.md)** - Explication complète de l'architecture
3. **[VALIDATION_REPORT.md](VALIDATION_REPORT.md)** - Résultats des tests (9/9 passés ✅)

---

## 📖 Documentation principale

### 📋 Guides d'utilisation

| Document | Description | Pour qui ? |
|---|---|---|
| [README.md](README.md) | Vue d'ensemble, installation, commandes | Tout le monde |
| [NEXT_STEPS.md](NEXT_STEPS.md) | Prochaines étapes après le déploiement | Utilisateurs AWS |
| [STATUS.md](STATUS.md) | État actuel du déploiement | Suivi de projet |

### 🏗️ Architecture technique

| Document | Description | Pour qui ? |
|---|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Explication détaillée de tous les composants | Développeurs, Ops |
| [diagrams/](diagrams/) | 6 diagrammes PlantUML de l'architecture | Présentation, apprentissage |
| [diagrams/README.md](diagrams/README.md) | Comment générer les diagrammes | Utilisateurs des diagrammes |

### ✅ Validation et tests

| Document | Description | Pour qui ? |
|---|---|---|
| [VALIDATION_REPORT.md](VALIDATION_REPORT.md) | Rapport complet : 9/9 tests passés | Validation, audit |
| [tests/validation.sh](tests/validation.sh) | Script de test automatique | Ops, CI/CD |

### 🎤 Présentation

| Document | Description | Pour qui ? |
|---|---|---|
| [PRESENTATION.md](PRESENTATION.md) | Guide pour présenter à tes camarades | Présentateurs |

---

## 🛠️ Scripts et outils

### Scripts de provisioning

| Script | Description | Usage |
|---|---|---|
| [scripts/provision-aws.sh](scripts/provision-aws.sh) | Créer/détruire l'infra AWS | `./provision-aws.sh up ~/.ssh/gandal.pub` |
| [scripts/deploy-alice.sh](scripts/deploy-alice.sh) | Déployer l'app de test (Alice) | `./scripts/deploy-alice.sh 16.170.20.250` |
| [scripts/run-validation.sh](scripts/run-validation.sh) | Lancer les tests | `./scripts/run-validation.sh 16.170.20.250` |
| [scripts/ssh-kubectl.sh](scripts/ssh-kubectl.sh) | Exécuter kubectl à distance | `./scripts/ssh-kubectl.sh kubectl get pods` |

### Scripts d'installation

| Script | Description | Usage |
|---|---|---|
| [install.sh](install.sh) | Installer K3s + registry sur la VM | `./install.sh <IP_PUBLIQUE>` |

### Application PaaS

| Script | Description | Usage |
|---|---|---|
| [gandal_deploy.py](gandal_deploy.py) | Script Python de déploiement | `python gandal_deploy.py deploy ...` |
| [registry.yaml](registry.yaml) | Manifeste du registry privé | (inclus dans install.sh) |

---

## 📊 Diagrammes disponibles

Tous les diagrammes sont dans le dossier [diagrams/](diagrams/).

### Vue d'ensemble

| Diagramme | Fichier | Description |
|---|---|---|
| **Architecture globale** | [architecture-globale.puml](diagrams/architecture-globale.puml) | Infrastructure AWS complète (VPC, EC2, Elastic IP) |
| **Architecture K3s** | [architecture-k3s.puml](diagrams/architecture-k3s.puml) | Composants internes K3s (namespaces, pods, services) |

### Flux et séquences

| Diagramme | Fichier | Description |
|---|---|---|
| **Flux de déploiement** | [flux-deploiement.puml](diagrams/flux-deploiement.puml) | Les 9 étapes du déploiement d'une app |
| **Flux HTTP** | [flux-http.puml](diagrams/flux-http.puml) | Requête HTTP de bout en bout (client → pod) |

### Sécurité

| Diagramme | Fichier | Description |
|---|---|---|
| **Isolation réseau** | [isolation-reseau.puml](diagrams/isolation-reseau.puml) | NetworkPolicy et flux bloqués/autorisés |
| **Quotas et limites** | [quotas-limites.puml](diagrams/quotas-limites.puml) | Validation des ResourceQuotas |

**Génération** : `cd diagrams/ && plantuml *.puml`

---

## 🎯 Par cas d'usage

### Je veux comprendre l'architecture

1. Lis [ARCHITECTURE.md](ARCHITECTURE.md) (documentation complète)
2. Regarde les diagrammes dans [diagrams/](diagrams/)
3. Consulte [VALIDATION_REPORT.md](VALIDATION_REPORT.md) pour voir les résultats

### Je veux déployer sur AWS

1. Lis [README.md](README.md) - Section "Phase 1"
2. Exécute `scripts/provision-aws.sh up ~/.ssh/gandal.pub`
3. Suis les instructions dans [NEXT_STEPS.md](NEXT_STEPS.md)

### Je veux présenter à mes camarades

1. Génère les diagrammes : `cd diagrams/ && plantuml *.puml`
2. Lis [PRESENTATION.md](PRESENTATION.md) (guide complet de présentation)
3. Prépare une démo ou utilise les PNG des diagrammes

### Je veux valider que tout fonctionne

1. Exécute [scripts/run-validation.sh](scripts/run-validation.sh)
2. Consulte les résultats dans le terminal
3. Compare avec [VALIDATION_REPORT.md](VALIDATION_REPORT.md)

### Je veux adapter pour XCP-ng

1. Lis [README.md](README.md) - Section "Passage à XCP-ng"
2. Consulte [ARCHITECTURE.md](ARCHITECTURE.md) - Section 8.3 (ce qui change)
3. Les scripts Python et K3s sont identiques, seule l'infra change

---

## 📐 Structure du projet

```
gandal-paas/
├── README.md                   # 📘 Guide principal
├── ARCHITECTURE.md             # 🏗️ Documentation architecture
├── VALIDATION_REPORT.md        # ✅ Rapport de validation
├── PRESENTATION.md             # 🎤 Guide de présentation
├── NEXT_STEPS.md               # 🔜 Prochaines étapes
├── STATUS.md                   # 📊 État du déploiement
├── INDEX.md                    # 📚 Ce fichier (navigation)
│
├── gandal_deploy.py            # 🐍 Script PaaS principal
├── install.sh                  # 🔧 Installation K3s + registry
├── registry.yaml               # 📦 Manifeste du registry
│
├── scripts/                    # 🛠️ Scripts d'infrastructure
│   ├── provision-aws.sh        #   Provisioning AWS
│   ├── deploy-alice.sh         #   Déploiement app de test
│   ├── run-validation.sh       #   Lancement des tests
│   ├── ssh-kubectl.sh          #   kubectl distant
│   ├── repair-access.sh        #   Réparation SSH
│   ├── add-pc-key.sh           #   Ajout clé SSH
│   └── open-sg.sh              #   Ouverture Security Group
│
├── diagrams/                   # 🎨 Diagrammes PlantUML
│   ├── README.md               #   Guide génération
│   ├── architecture-globale.puml
│   ├── architecture-k3s.puml
│   ├── flux-deploiement.puml
│   ├── flux-http.puml
│   ├── isolation-reseau.puml
│   └── quotas-limites.puml
│
├── tests/                      # 🧪 Tests de validation
│   └── validation.sh           #   9 tests automatiques
│
├── .gitignore                  # 🚫 Fichiers ignorés par git
└── explication_v3.tex          # 📄 Document LaTeX (cadrage)
└── simulation_v3.tex           # 📄 Document LaTeX (procédure)
```

---

## 🔗 Liens rapides

### Documentation externe

- [Kubernetes officiel](https://kubernetes.io/docs/)
- [K3s Documentation](https://docs.k3s.io/)
- [Traefik Documentation](https://doc.traefik.io/traefik/)
- [PlantUML](https://plantuml.com/)
- [sslip.io](https://sslip.io/)

### Dépôt GitHub

- **URL** : https://github.com/Djusse/gandal-paas
- **Branches** : `main` (stable)
- **Issues** : Pour signaler des bugs ou proposer des améliorations

---

## 💡 Conseils de lecture

### Pour les débutants

1. **Commence par** : [README.md](README.md)
2. **Regarde** : Les diagrammes dans [diagrams/](diagrams/)
3. **Lis** : [ARCHITECTURE.md](ARCHITECTURE.md) sections 1-2

### Pour les développeurs

1. **Comprends** : [ARCHITECTURE.md](ARCHITECTURE.md) en entier
2. **Étudie** : [gandal_deploy.py](gandal_deploy.py)
3. **Teste** : [tests/validation.sh](tests/validation.sh)

### Pour les ops

1. **Déploie** : Suis [README.md](README.md) Phase 1-2
2. **Valide** : [scripts/run-validation.sh](scripts/run-validation.sh)
3. **Documente** : [VALIDATION_REPORT.md](VALIDATION_REPORT.md)

---

## 📝 Glossaire rapide

| Terme | Définition |
|---|---|
| **PaaS** | Platform as a Service - Plateforme qui gère l'infra pour toi |
| **K3s** | Kubernetes léger (70 Mo vs 1 Go) |
| **Namespace** | Isolation logique dans Kubernetes |
| **Ingress** | Routeur HTTP pour exposer les apps |
| **ResourceQuota** | Limite de ressources par projet |
| **NetworkPolicy** | Pare-feu réseau Kubernetes |
| **ClusterIP** | IP interne pour un Service |
| **sslip.io** | DNS wildcard automatique |

---

## ✅ Checklist complète

### Déploiement AWS

- [ ] Générer la clé SSH (`ssh-keygen`)
- [ ] Provisionner AWS (`scripts/provision-aws.sh up`)
- [ ] Installer K3s (`install.sh`)
- [ ] Publier les images (nginx, curl)
- [ ] Déployer Alice (`scripts/deploy-alice.sh`)
- [ ] Valider (`scripts/run-validation.sh`)
- [ ] Détruire (`scripts/provision-aws.sh down`)

### Présentation

- [ ] Générer les diagrammes (`plantuml diagrams/*.puml`)
- [ ] Lire [PRESENTATION.md](PRESENTATION.md)
- [ ] Créer les slides (PowerPoint/Google Slides)
- [ ] Préparer la démo
- [ ] Tester le timing (20-30 min)
- [ ] Distribuer la documentation

### Documentation

- [ ] Lire [README.md](README.md)
- [ ] Lire [ARCHITECTURE.md](ARCHITECTURE.md)
- [ ] Comprendre les diagrammes
- [ ] Consulter [VALIDATION_REPORT.md](VALIDATION_REPORT.md)

---

## 🆘 Besoin d'aide ?

### Problèmes courants

| Problème | Solution | Document |
|---|---|---|
| kubectl ne fonctionne pas | Export KUBECONFIG | [STATUS.md](STATUS.md) |
| Pods ne démarrent pas | Vérifier quotas et logs | [ARCHITECTURE.md](ARCHITECTURE.md) section 4 |
| URL ne répond pas | Vérifier Ingress et Traefik | [ARCHITECTURE.md](ARCHITECTURE.md) section 7 |
| Tests échouent | Attendre metrics-server | [VALIDATION_REPORT.md](VALIDATION_REPORT.md) |

### Où trouver l'info ?

- **Commandes kubectl** : [ARCHITECTURE.md](ARCHITECTURE.md) Annexe B
- **Variables d'env** : [README.md](README.md) + [ARCHITECTURE.md](ARCHITECTURE.md) Annexe A
- **Ports utilisés** : [ARCHITECTURE.md](ARCHITECTURE.md) Annexe D
- **Coûts AWS** : [STATUS.md](STATUS.md) + [VALIDATION_REPORT.md](VALIDATION_REPORT.md)

---

## 📊 État du projet

**Version** : 1.0 (Prototype validé)  
**Date** : 28 octobre 2026  
**Statut** : ✅ Tests validés (9/9)  
**Infra** : AWS eu-north-1 (pour migration XCP-ng)  
**Prochaine étape** : Déploiement sur XCP-ng

---

**Bonne lecture et bon développement ! 🚀**
