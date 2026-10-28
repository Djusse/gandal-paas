# Diagrammes PlantUML - Architecture GANDAL PaaS

Ce répertoire contient 6 diagrammes détaillés de l'architecture GANDAL PaaS.

## Fichiers disponibles

| Fichier | Description |
|---|---|
| `architecture-globale.puml` | Vue d'ensemble AWS (VPC, EC2, Elastic IP, Security Groups) |
| `architecture-k3s.puml` | Architecture interne K3s (namespaces, composants système, pods) |
| `quotas-limites.puml` | Diagramme de séquence : validation des quotas |
| `isolation-reseau.puml` | NetworkPolicy et flux réseau (autorisés/bloqués) |
| `flux-deploiement.puml` | Séquence complète de déploiement d'une application |
| `flux-http.puml` | Flux HTTP de bout en bout (client → pod nginx) |

## Génération des images

### Prérequis

Installer PlantUML :

**Sur Ubuntu/Debian** :
```bash
sudo apt-get install plantuml
```

**Sur macOS** :
```bash
brew install plantuml
```

**Ou avec Java** :
```bash
# Télécharger plantuml.jar
wget https://sourceforge.net/projects/plantuml/files/plantuml.jar/download -O plantuml.jar

# Utiliser avec :
java -jar plantuml.jar fichier.puml
```

### Génération

**Tous les diagrammes** :
```bash
cd diagrams/
plantuml *.puml
```

Cela génère les fichiers PNG dans le même répertoire.

**Un seul diagramme** :
```bash
plantuml architecture-globale.puml
```

**Format SVG** (vectoriel, meilleure qualité) :
```bash
plantuml -tsvg *.puml
```

**Format PDF** :
```bash
plantuml -tpdf *.puml
```

### Options utiles

**Mode watch** (regénère automatiquement à chaque modification) :
```bash
plantuml -gui architecture-globale.puml
```

**Spécifier un charset** :
```bash
plantuml -charset UTF-8 *.puml
```

## Visualisation en ligne

Si PlantUML n'est pas installé, tu peux visualiser les diagrammes en ligne :

1. Ouvrir [PlantUML Online Editor](http://www.plantuml.com/plantuml/uml/)
2. Copier-coller le contenu d'un fichier `.puml`
3. Le diagramme s'affiche instantanément

**Ou utiliser l'extension VS Code** :
- Extension : "PlantUML" par jebbs
- Ouvre un fichier `.puml` et appuie sur `Alt+D` pour prévisualiser

## Intégration dans la documentation

Les diagrammes peuvent être inclus dans Markdown :

```markdown
![Architecture globale](diagrams/architecture-globale.png)
```

Ou dans LaTeX :

```latex
\begin{figure}[h]
  \centering
  \includegraphics[width=\textwidth]{diagrams/architecture-globale.png}
  \caption{Architecture globale GANDAL PaaS sur AWS}
\end{figure}
```

## Modification des diagrammes

Les fichiers `.puml` sont du texte brut. Pour modifier :

1. Ouvrir le fichier `.puml` dans un éditeur
2. Modifier le code PlantUML
3. Regénérer avec `plantuml fichier.puml`

**Exemple** : Changer la couleur d'un composant :
```plantuml
' Avant
component "Traefik" as traefik

' Après
component "Traefik" as traefik #lightblue
```

## Thèmes PlantUML

Pour changer le style de tous les diagrammes :

```plantuml
@startuml
!theme plain      ' Thème par défaut (utilisé actuellement)
!theme bluegray   ' Thème moderne gris-bleu
!theme cerulean   ' Thème bleu vif
!theme superhero  ' Thème sombre
@enduml
```

Modifier la ligne `!theme` en haut de chaque fichier `.puml`.

## Ressources

- [Documentation PlantUML](https://plantuml.com/)
- [Guide diagrammes de séquence](https://plantuml.com/sequence-diagram)
- [Guide diagrammes de composants](https://plantuml.com/component-diagram)
- [AWS Icons for PlantUML](https://github.com/awslabs/aws-icons-for-plantuml)
- [Thèmes disponibles](https://plantuml.com/theme)

## Exemples de sortie

Après génération, tu auras :

```
diagrams/
├── README.md
├── architecture-globale.puml
├── architecture-globale.png         ← Généré
├── architecture-k3s.puml
├── architecture-k3s.png             ← Généré
├── quotas-limites.puml
├── quotas-limites.png               ← Généré
├── isolation-reseau.puml
├── isolation-reseau.png             ← Généré
├── flux-deploiement.puml
├── flux-deploiement.png             ← Généré
├── flux-http.puml
└── flux-http.png                    ← Généré
```

Les fichiers `.png` peuvent être utilisés dans des présentations, rapports, ou documentation.
