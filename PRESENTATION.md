# Guide de présentation GANDAL PaaS

Ce document te guide pour expliquer l'architecture GANDAL PaaS à tes camarades de manière claire et structurée.

---

## 🎯 Objectif de la présentation

Expliquer comment fonctionne un **PaaS multi-tenant** basé sur Kubernetes, depuis l'infrastructure AWS jusqu'à l'accès HTTP d'un utilisateur final.

**Durée suggérée** : 20-30 minutes

---

## 📋 Plan de présentation

### 1. Introduction (3 min)

**Slide 1 : Qu'est-ce que GANDAL PaaS ?**

"GANDAL PaaS est une plateforme qui permet à plusieurs utilisateurs de déployer leurs applications web de manière isolée sur une infrastructure partagée."

**Problème résolu** :
- Sans PaaS : Chaque dev doit gérer son serveur, sa config réseau, sa sécurité
- Avec PaaS : Un simple `deploy alice memoire my-api` crée tout automatiquement

**Analogie** : "C'est comme Heroku ou Vercel, mais on le construit nous-mêmes pour comprendre la mécanique."

**Slide 2 : Périmètre du prototype**

"On valide sur AWS avant de déployer sur l'infra XCP-ng définitive."

| Composant | AWS | XCP-ng |
|---|---|---|
| VM | EC2 | VM XCP-ng |
| DNS | sslip.io | DNS GANDAL |
| K3s | ✅ Identique | ✅ Identique |
| Scripts | ✅ Identiques | ✅ Identiques |

---

### 2. Architecture globale (5 min)

**Slide 3 : Vue d'ensemble** → `diagrams/architecture-globale.png`

"Voici l'infrastructure complète sur AWS."

**Expliquer de gauche à droite** :

1. **Utilisateur sur Internet**
   - Tape l'URL dans son navigateur
   - Exemple : `http://my-api-memoire-alice.16.170.20.250.sslip.io`

2. **DNS sslip.io**
   - Service gratuit qui résout automatiquement
   - `*.16.170.20.250.sslip.io` → `16.170.20.250`
   - **Astuce** : Pas besoin de configurer un DNS !

3. **Elastic IP (16.170.20.250)**
   - IP publique fixe attachée à notre VM
   - Permet le DNS wildcard

4. **VPC AWS (10.0.0.0/16)**
   - Réseau privé isolé
   - Sous-réseau public pour la VM

5. **Security Group (pare-feu)**
   - Port 22 (SSH) : Admin seulement
   - Port 80 (HTTP) : Public
   - Port 6443 (K8s API) : Admin seulement
   - **Port 5000 NON ouvert** : Registry privé

6. **Instance EC2**
   - m7i-flex.large : 2 vCPU, 8 Go RAM
   - Ubuntu 24.04 LTS
   - K3s + registry + apps

**Points clés** :
- ✅ Infrastructure as Code (script provision-aws.sh)
- ✅ Sécurité par défaut (ports fermés sauf nécessaire)
- ✅ Reproductible en quelques minutes

---

### 3. Architecture K3s (7 min)

**Slide 4 : K3s vs Kubernetes standard**

"K3s est une version allégée de Kubernetes."

| Aspect | Kubernetes | K3s |
|---|---|---|
| Taille binaire | ~1 Go | 70 Mo |
| RAM requise | 2-4 Go | 512 Mo |
| Base de données | etcd (cluster) | SQLite |
| Ingress | À installer | Traefik inclus |
| Idéal pour | Production cloud | Edge, IoT, démos |

**Pourquoi K3s ?**
- ✅ Plus simple à installer
- ✅ Toutes les fonctionnalités Kubernetes
- ✅ Parfait pour un cluster single-node

**Slide 5 : Composants K3s** → `diagrams/architecture-k3s.png`

"Voici ce qui tourne sur la VM."

**Expliquer les namespaces** (isolation logique) :

1. **kube-system** (composants système)
   - **Traefik** : Routeur HTTP (Ingress Controller)
   - **CoreDNS** : Résolution DNS interne
   - **metrics-server** : Collecte CPU/RAM
   - **local-path provisioner** : Stockage des volumes

2. **gandal-system** (infra GANDAL)
   - **Registry privé** : localhost:5000
   - Stockage : 10 Go (PVC)
   - Images : nginx, curl, futures apps

3. **project-alice-memoire** (projet d'Alice)
   - **ResourceQuota** : Max 4 pods, 2 CPU, 2 Gi RAM
   - **LimitRange** : Valeurs par défaut (500m CPU, 512Mi RAM)
   - **NetworkPolicy** : Isolation réseau
   - **Deployment my-api** : 2 réplicas nginx
   - **Service** : ClusterIP (accès interne)
   - **Ingress** : Exposition publique

4. **project-bob-test** (projet de Bob)
   - Même structure, isolation totale

**Points clés** :
- ✅ Chaque utilisateur a son namespace
- ✅ Impossible de dépasser les quotas
- ✅ Bob ne peut pas accéder aux données d'Alice

---

### 4. Isolation et sécurité (5 min)

**Slide 6 : Isolation réseau** → `diagrams/isolation-reseau.png`

"Comment on empêche Bob de lire les données d'Alice ?"

**NetworkPolicy expliquée simplement** :

```yaml
# Par défaut : TOUT est bloqué
# On autorise explicitement :
ingress:
  - from: même namespace   # Alice ↔ Alice ✅
  - from: kube-system      # Traefik → Alice ✅
  # Tout le reste est BLOQUÉ
  # Bob → Alice ❌
```

**Démonstration du test 3** :

1. On crée un pod "sonde" dans le namespace de Bob
2. On essaie de curl vers Alice : `curl http://my-api.project-alice-memoire.svc`
3. **Résultat** : `Connection timeout` → Bloqué ! ✅

**Slide 7 : Quotas de ressources** → `diagrams/quotas-limites.png`

"Comment on empêche Alice de consommer tout le cluster ?"

**Scénario** :

1. Alice demande 10 réplicas (`kubectl scale --replicas=10`)
2. Chaque pod demande 100m CPU, 128Mi RAM
3. **Calcul** :
   - 10 pods × 100m = 1 CPU ✅ (quota: 1 CPU)
   - 10 pods × 128Mi = 1280Mi ❌ (quota: 1 Gi = 1024Mi)
   - 10 pods > 4 ❌ (quota: 4 pods)
4. **Résultat** : Kubernetes crée seulement 4 pods
5. **Events** : `FailedCreate: exceeded quota`

**Points clés** :
- ✅ Protection du cluster
- ✅ Fair-use entre utilisateurs
- ✅ Prédictibilité des coûts

---

### 5. Flux de déploiement (5 min)

**Slide 8 : Du code à l'URL** → `diagrams/flux-deploiement.png`

"Que se passe-t-il quand on exécute `gandal_deploy.py deploy alice memoire my-api` ?"

**Les 9 étapes** :

1. **Namespace** : Création de `project-alice-memoire`
2. **LimitRange** : Valeurs par défaut des ressources
3. **ResourceQuota** : Plafond du projet
4. **NetworkPolicy** : Isolation réseau
5. **Deployment** : Création de 2 pods nginx
6. **Service** : ClusterIP pour load balancing
7. **Ingress** : Route HTTP externe
8. **Pull image** : Téléchargement depuis le registry
9. **Vérification** : Attente des pods Ready

**Durée totale** : ~30 secondes

**Résultat** : `http://my-api-memoire-alice.16.170.20.250.sslip.io` est accessible !

**Code Python simplifié** :

```python
def deploy(user, project, app, image, port):
    ns = f"project-{user}-{project}"
    host = f"{app}-{project}-{user}.{BASE_DOMAIN}"
    
    # Créer toutes les ressources
    create_namespace(ns, labels={owner: user})
    create_quota(ns)
    create_networkpolicy(ns)
    create_deployment(ns, app, image, port)
    create_service(ns, app, port)
    create_ingress(ns, app, host)
    
    print(f"✅ Déployé sur http://{host}")
```

---

### 6. Flux HTTP (5 min)

**Slide 9 : Requête utilisateur** → `diagrams/flux-http.png`

"Que se passe-t-il quand un utilisateur visite l'URL ?"

**Les 9 étapes** :

1. **DNS** :
   - Client : "Quelle est l'IP de my-api-memoire-alice.16.170.20.250.sslip.io ?"
   - sslip.io : "C'est 16.170.20.250"

2. **TCP** :
   - Client → Elastic IP : `SYN` sur port 80
   - Security Group : Port 80 autorisé ✅
   - EC2 : `SYN-ACK`

3. **HTTP** :
   - Client : `GET / HTTP/1.1`
   - Header : `Host: my-api-memoire-alice.16.170.20.250.sslip.io`

4. **Traefik** (Ingress Controller) :
   - Lit le header `Host`
   - Lookup dans les routes : "C'est l'app d'Alice !"
   - Forward vers `my-api.project-alice-memoire.svc:80`

5. **CoreDNS** :
   - Résolution interne : `my-api...svc.cluster.local` → `10.43.5.10`

6. **Service** (Load Balancer) :
   - ClusterIP 10.43.5.10 reçoit la requête
   - Round-robin : Choisit pod1 (10.42.0.11) ou pod2 (10.42.0.12)

7. **Pod nginx** :
   - Lit `/usr/share/nginx/html/index.html`
   - Génère réponse HTTP 200

8. **Retour** :
   - Pod → Service → Traefik → EC2 → Elastic IP → Internet

9. **Client** :
   - Affiche la page HTML nginx

**Analogie** : "C'est comme La Poste qui livre un courrier avec plusieurs intermédiaires."

---

### 7. Tests de validation (3 min)

**Slide 10 : Les 9 tests**

"Comment on vérifie que tout fonctionne ?"

| # | Test | Validation |
|---|---|---|
| 1 | Déploiement | Namespace + pods Running |
| 2 | DNS | curl HTTP 200 |
| 3 | Isolation | Bob ne peut pas joindre Alice |
| 4 | Résilience | Pods recréés après suppression |
| 5 | Quotas | Scale limité à 4 pods |
| 6 | Métriques | kubectl top fonctionne |
| 7 | Labels | Propriétaire correct |
| 8 | Idempotence | Re-déploiement sans erreur |
| 9 | Nettoyage | Suppression propre |

**Résultat** : **9/9 tests passés** ✅

**Commande** :
```bash
./tests/validation.sh alice memoire my-api
# Bilan :
#   Réussis  : 9
#   Échoués  : 0
#   Ignorés  : 1
# RESULTAT : prototype valide.
```

---

### 8. Démonstration live (2-3 min)

**Option A : Sur l'infra AWS (si encore déployée)**

```bash
# Se connecter à la VM
ssh -i ~/.ssh/gandal ubuntu@16.170.20.250

# Vérifier le cluster
kubectl get nodes
kubectl get pods -A

# Tester l'URL
curl http://my-api-memoire-alice.16.170.20.250.sslip.io

# Scale up
kubectl scale deployment my-api -n project-alice-memoire --replicas=10
kubectl get pods -n project-alice-memoire
# → Seulement 4 pods (quota)

# Voir les événements
kubectl get events -n project-alice-memoire | grep quota
```

**Option B : Avec les diagrammes**

Montrer les diagrammes générés (PNG) et suivre le flux HTTP pas à pas.

---

### 9. Architecture pour XCP-ng (2 min)

**Slide 11 : Passage à XCP-ng**

"Qu'est-ce qui change pour la prod ?"

| Composant | AWS (prototype) | XCP-ng (prod) | Effort |
|---|---|---|---|
| VM | EC2 | VM XCP-ng | ⚠️ Nouveau provisioning |
| DNS | sslip.io | DNS GANDAL | ⚠️ Configuration DNS |
| K3s | ✅ Identique | ✅ Identique | ✅ Aucun |
| Registry | HTTP | HTTPS + auth | ⚠️ Config TLS |
| Scripts | ✅ Identiques | ✅ Identiques | ✅ Aucun |
| Certificats | Aucun | cert-manager | ⚠️ Let's Encrypt |

**Code portable à 100%** : Les scripts Python, les manifests Kubernetes, la logique métier ne changent pas !

---

### 10. Questions fréquentes (backup)

**Q : Pourquoi K3s et pas Kubernetes standard ?**
A : Plus simple pour un cluster single-node, toutes les features Kubernetes, 10× plus léger.

**Q : Pourquoi un registry privé ?**
A : Pour héberger nos propres images sans dépendre de Docker Hub (rate limits, sécurité).

**Q : Les quotas sont-ils obligatoires ?**
A : Oui en multi-tenant ! Sinon un utilisateur peut planter le cluster.

**Q : Traefik vs nginx Ingress ?**
A : Traefik est inclus dans K3s, configuration dynamique (pas de reload), dashboard web.

**Q : sslip.io est-il fiable en prod ?**
A : Non, c'est pour la démo uniquement. En prod : DNS GANDAL avec wildcard.

**Q : Peut-on avoir plusieurs nœuds K3s ?**
A : Oui ! K3s supporte le HA (High Availability) avec plusieurs masters et workers.

**Q : Comment on sauvegarde les données ?**
A : Velero (backup Kubernetes), snapshots du PVC, backup etcd.

---

## 🎨 Conseils de présentation

### Préparation

1. **Générer les diagrammes** :
   ```bash
   cd diagrams/
   plantuml *.puml
   ```

2. **Créer une présentation PowerPoint/Google Slides** :
   - Importer les PNG des diagrammes
   - Ajouter des titres et bullets points
   - Préparer des notes de speaker

3. **Tester la démo** :
   - Si l'infra AWS est encore up : préparer les commandes
   - Sinon : préparer des screenshots

### Pendant la présentation

✅ **À faire** :
- Expliquer avec des analogies (Poste, immeuble avec appartements)
- Pointer sur les diagrammes avec le curseur
- Parler lentement et clairement
- Faire des pauses pour les questions

❌ **À éviter** :
- Lire les slides mot à mot
- Aller trop vite dans les détails techniques
- Supposer que tout le monde connaît Kubernetes
- Oublier de conclure

### Structure d'explication idéale

Pour chaque composant :

1. **Problème** : "Sans X, on aurait ce problème..."
2. **Solution** : "X permet de résoudre ça en faisant..."
3. **Démonstration** : "Voici comment ça fonctionne concrètement..."
4. **Bénéfice** : "Grâce à X, on obtient..."

**Exemple (NetworkPolicy)** :

1. **Problème** : "Par défaut, Bob peut accéder aux données d'Alice dans Kubernetes."
2. **Solution** : "La NetworkPolicy bloque tout le trafic sauf ce qu'on autorise explicitement."
3. **Démonstration** : (montrer le diagramme avec les flux rouges bloqués)
4. **Bénéfice** : "Chaque utilisateur est complètement isolé, comme des appartements séparés."

---

## 📚 Documents de support

À distribuer à tes camarades :

1. **ARCHITECTURE.md** : Documentation complète
2. **VALIDATION_REPORT.md** : Résultats des tests
3. **Diagrammes PNG** : Visuels pour étudier
4. **README.md** : Guide d'installation

**Suggestion** : Créer un Google Drive ou repo GitHub avec tout ça.

---

## 🎯 Checklist avant la présentation

- [ ] Générer tous les diagrammes PNG
- [ ] Tester l'ouverture des PNG (pas corrompus)
- [ ] Créer la présentation (slides)
- [ ] Relire ARCHITECTURE.md
- [ ] Préparer les commandes de démo (si live)
- [ ] Tester la démo (si live)
- [ ] Prévoir des questions/réponses
- [ ] Chronométrer la présentation (20-30 min)
- [ ] Envoyer les docs aux camarades la veille

---

## 💡 Variantes de présentation

### Version courte (10 min)

1. Intro + objectif (2 min)
2. Architecture globale (3 min)
3. Flux HTTP (3 min)
4. Tests validés (2 min)

### Version longue (45 min)

Ajouter :
- Détail du code Python (`gandal_deploy.py`)
- Détail des manifests Kubernetes
- Comparaison avec d'autres PaaS (Heroku, Vercel)
- Feuille de route (évolutions futures)

### Version technique (1h+)

Ajouter :
- Démonstration live complète
- Code review des scripts
- Exercice pratique (les camarades déploient une app)
- Q&A étendu

---

## 📞 Ressources supplémentaires

**Si quelqu'un veut creuser** :

- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [K3s Documentation](https://docs.k3s.io/)
- [PlantUML Guide](https://plantuml.com/)
- [CNCF Landscape](https://landscape.cncf.io/)

**Dépôt GitHub** : https://github.com/Djusse/gandal-paas

**Contact** : [Ton email ou Discord]

---

## ✅ Conclusion type

"On a démontré qu'on peut construire un PaaS multi-tenant avec :
- ✅ Isolation forte (namespaces + NetworkPolicies)
- ✅ Quotas par projet
- ✅ Déploiement en 30 secondes
- ✅ Code 100% portable sur XCP-ng

Le prototype valide la faisabilité technique. Prochaine étape : déploiement sur l'infra définitive avec TLS et authentification."

---

**Bonne présentation ! 🚀**
