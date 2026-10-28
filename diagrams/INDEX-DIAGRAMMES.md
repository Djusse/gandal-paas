# Index des diagrammes GANDAL PaaS

## ✅ Diagrammes compilés (12 images PNG)

### 📊 Nouveaux diagrammes simplifiés (compatibles présentation)

| # | Fichier | Description | Taille |
|---|---|---|---|
| 1 | `01-architecture-simple.png` | Architecture globale AWS simplifiée | 117 KB |
| 2 | `02-k3s-namespaces.png` | Organisation des namespaces K3s | 76 KB |
| 3 | `03-flux-deploiement-simple.png` | Flux de déploiement simplifié | 69 KB |
| 4 | `04-flux-http-simple.png` | Requête HTTP de bout en bout | 59 KB |
| 5 | `05-isolation-reseau.png` | NetworkPolicy et isolation | 61 KB |
| 6 | `06-quotas.png` | Gestion des quotas (scénario scale) | 73 KB |

### 📐 Diagrammes originaux (détaillés)

| # | Fichier | Description | Taille |
|---|---|---|---|
| 7 | `architecture-globale.png` | Infrastructure AWS complète | 5.5 KB |
| 8 | `architecture-k3s.png` | Composants K3s détaillés | 5.3 KB |
| 9 | `flux-deploiement.png` | Séquence de déploiement complète | 5.2 KB |
| 10 | `flux-http.png` | Flux HTTP complet (9 étapes) | 4.6 KB |
| 11 | `isolation-reseau.png` | NetworkPolicy détaillée | 4.9 KB |
| 12 | `quotas-limites.png` | Validation des ResourceQuotas | 5.0 KB |

## 🎨 Recommandations d'usage

### Pour une présentation (PowerPoint/Google Slides)

**Utilisez les diagrammes 01-06 (simplifiés)** :
- ✅ Plus lisibles en petit format
- ✅ Texte plus gros
- ✅ Couleurs contrastées
- ✅ Légendes claires

**Ordre suggéré** :
1. 01-architecture-simple.png (vue d'ensemble)
2. 02-k3s-namespaces.png (composants internes)
3. 03-flux-deploiement-simple.png (comment ça marche)
4. 04-flux-http-simple.png (flux utilisateur)
5. 05-isolation-reseau.png (sécurité)
6. 06-quotas.png (gestion des ressources)

### Pour la documentation technique

**Utilisez les deux versions** :
- Diagrammes simplifiés pour les introductions
- Diagrammes détaillés pour les explications approfondies

## 🔄 Regénération

Si tu modifies un fichier `.puml` :

```bash
cd diagrams/
plantuml nom-du-fichier.puml
```

Pour tout regénérer :

```bash
cd diagrams/
plantuml *.puml
```

## 📝 Correspondance fichiers sources

| Image PNG | Fichier source PUML |
|---|---|
| `01-architecture-simple.png` | `01-architecture-simple.puml` |
| `02-k3s-namespaces.png` | `02-k3s-namespaces.puml` |
| `03-flux-deploiement-simple.png` | `03-flux-deploiement-simple.puml` |
| `04-flux-http-simple.png` | `04-flux-http-simple.puml` |
| `05-isolation-reseau.png` | `05-isolation-reseau.puml` |
| `06-quotas.png` | `06-quotas.puml` |
| `architecture-globale.png` | `architecture-globale.puml` |
| `architecture-k3s.png` | `architecture-k3s.puml` |
| `flux-deploiement.png` | `flux-deploiement.puml` |
| `flux-http.png` | `flux-http.puml` |
| `isolation-reseau.png` | `isolation-reseau.puml` |
| `quotas-limites.png` | `quotas-limites.puml` |

## 🖼️ Visualisation

### Sur Linux
```bash
eog 01-architecture-simple.png
# ou
xdg-open 01-architecture-simple.png
```

### Tous les diagrammes
```bash
eog diagrams/*.png
```

## 📊 Statistiques

- **Total images** : 12
- **Taille totale** : ~550 KB
- **Diagrammes simplifiés** : 6 (optimisés présentation)
- **Diagrammes détaillés** : 6 (documentation technique)

## ✨ Prêt pour la présentation !

Tous les diagrammes sont maintenant disponibles en PNG. Tu peux :
1. Les insérer dans des slides
2. Les partager avec tes camarades
3. Les imprimer pour une présentation physique
4. Les inclure dans un rapport

**Bon courage pour ta présentation ! 🎤**
