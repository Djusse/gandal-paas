# Guide — Déploiement en direct d'une landing page

> Document de préparation à une démonstration live du prototype GANDAL PaaS.
> Public visé : camarades de promotion, jury, équipe projet.
> Durée du live : **6 à 8 minutes**. Durée de préparation : **20 à 30 minutes**.

---

## Ce que la démo doit prouver

En 6 à 8 minutes, l'audience doit voir trois choses qu'aucune slide ne peut montrer :

1. **Du vide au public** : un namespace inexistant devient une URL visitable en une commande.
2. **Aucune intervention manuelle** : ni YAML écrit à la main, ni `kubectl apply`. Tout passe par [`gandal_deploy.py`](gandal_deploy.py:76).
3. **Le PaaS, pas seulement Kubernetes** : quotas, isolation et labels sont créés *avant* l'application, par le même appel.

Le principe de la démo : **tout ce qui est risqué se prépare avant ; en direct, on ne fait que la commande `deploy` et des observations.** La construction d'image est faite à l'avance, les images sont déjà dans le registry, les DNS sont déjà chauds.

---

## 1. Préparation (la veille, 20 min)

### 1.1 Se connecter à la VM

```bash
ssh -i ~/gandal ubuntu@16.170.20.250
```

### 1.2 Créer la landing page

```bash
mkdir -p ~/landing && cd ~/landing
```

Contenu de `index.html` — **CSS inline, zéro dépendance externe** : aucune police, aucun CDN, donc aucun risque de page blanche si le réseau de la salle filtre :

```html
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GANDAL PaaS</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
       background:linear-gradient(135deg,#0f2027,#203a43,#2c5364);
       color:#fff;min-height:100vh;display:flex;align-items:center;justify-content:center}
  main{max-width:720px;padding:2rem;text-align:center}
  h1{font-size:3rem;letter-spacing:-.03em;margin-bottom:.5rem}
  .tag{display:inline-block;padding:.35rem .9rem;border-radius:999px;
       background:rgba(255,255,255,.12);font-size:.85rem;margin-bottom:1.5rem}
  p{font-size:1.1rem;line-height:1.7;opacity:.9}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
        gap:1rem;margin-top:2.5rem}
  .card{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.15);
        border-radius:12px;padding:1rem}
  .card b{display:block;font-size:1.6rem}
  .card span{font-size:.8rem;opacity:.7}
  footer{margin-top:2.5rem;font-size:.8rem;opacity:.55}
</style>
</head>
<body>
<main>
  <span class="tag">Déployé par GANDAL PaaS</span>
  <h1>Votre application, en une commande.</h1>
  <p>Cette page tourne dans un conteneur nginx, sur un pod Kubernetes,
     créé automatiquement dans un namespace isolé — avec ses quotas,
     sa NetworkPolicy et son nom DNS.</p>

  <div class="grid">
    <div class="card"><b>2</b><span>réplicas actifs</span></div>
    <div class="card"><b>1</b><span>commande tapée</span></div>
    <div class="card"><b>0</b><span>YAML écrit à la main</span></div>
  </div>

  <footer>namespace&nbsp;: project-alice-demo</footer>
</main>
</body>
</html>
```

Contenu de `Dockerfile` :

```dockerfile
FROM nginx:alpine
COPY index.html /usr/share/nginx/html/index.html
```

### 1.3 Construire et pousser les deux versions

Deux versions sont nécessaires : `v1` pour la démo initiale, `v2` pour la démo de mise à jour. **Ne jamais réutiliser le même tag** — voir le piège n°1 plus bas.

```bash
cd ~/landing

# Version 1
sudo docker build -t localhost:5000/landing:v1 .
sudo docker push localhost:5000/landing:v1

# Version 2 : on change le titre pour que le public voie la différence
sed -i 's/<h1>.*<\/h1>/<h1>Version 2, déployée en 8 secondes.<\/h1>/' index.html
sudo docker build -t localhost:5000/landing:v2 .
sudo docker push localhost:5000/landing:v2

# Vérification : les deux tags doivent apparaître
curl -s http://localhost:5000/v2/_catalog
curl -s http://localhost:5000/v2/landing/tags/list
```

Résultat attendu : `{"name":"landing","tags":["v1","v2"]}`.

### 1.4 Vérifier que le socle est sain

```bash
kubectl get nodes                       # Ready
kubectl get pods -A | grep -E 'traefik|coredns|metrics|registry'   # Running
kubectl -n gandal-system get deploy private-registry               # 1/1
```

### 1.5 Purger un éventuel déploiement précédent

La démo doit partir d'un état propre. Si `project-alice-demo` existe déjà :

```bash
python3 ~/gandal-paas/gandal_deploy.py delete alice demo --purge || true
kubectl get ns | grep demo              # ne doit rien renvoyer
```

> Si `project-alice-memoire` existe encore (namespace du test de validation), pense aussi à le purger pour libérer les ressources du nœud :
> ```bash
> python3 ~/gandal-paas/gandal_deploy.py delete alice memoire --purge || true
> python3 ~/gandal-paas/gandal_deploy.py delete bob test --purge || true
> kubectl get ns                          # seuls les namespaces système doivent rester
> ```

### 1.6 Pré-chauffer le DNS et le cache

```bash
# Force Traefik à connaître la future route : ce curl échouera en 404, c'est normal
curl -s -o /dev/null -w '%{http_code}\n' http://landing-demo-alice.16.170.20.250.sslip.io
```

Un `404` prouve que **sslip.io résout déjà et que Traefik répond** : le seul élément manquant est l'Ingress. C'est un excellent point à montrer au public juste avant la démo.

---

## 2. Checklist T-30 minutes

| Point | Commande de contrôle | Attendu |
|---|---|---|
| VM joignable | `ssh -i ~/gandal ubuntu@16.170.20.250 'uptime'` | réponse |
| Images présentes | `curl -s localhost:5000/v2/landing/tags/list` | `v1`,`v2` |
| Cluster sain | `kubectl get nodes` | `Ready` |
| Namespace absent | `kubectl get ns project-alice-demo` | `NotFound` |
| DNS résout | `curl -s -o /dev/null -w '%{http_code}\n' http://landing-demo-alice.16.170.20.250.sslip.io` | `404` |
| Navigateur de la salle | ouvrir `http://my-api-memoire-alice.16.170.20.250.sslip.io` | la page nginx du Test 2 |
| Terminal lisible | police ≥ 18 pt, fond sombre | — |
| Second terminal (slides narrateur) | prêt sur `kubectl get pods -w` | — |

> Le point « navigateur de la salle » est **le plus important** : si le réseau de l'établissement bloque sslip.io ou le port 80 sortant, la démo visuelle échoue même si tout fonctionne côté serveur. À tester dans la salle, pas ailleurs.

---

## 3. Déroulé en direct — 7 minutes

### Étape 0 — Le point de départ (30 s)

**Terminal 1** (sur la VM) :

```bash
source ~/gandal-venv/bin/activate
cd ~/gandal-paas
export GANDAL_BASE_DOMAIN="16.170.20.250.sslip.io"
export KUBECONFIG=$HOME/.kube/config
```

Ce que tu dis :

> « Voici l'état du cluster : un nœud, trois namespaces système, et aucun namespace applicatif. Aucune landing page n'existe. »

```bash
kubectl get ns
```

**Terminal 2** (la prévisualisation) :

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://landing-demo-alice.16.170.20.250.sslip.io
```

Ce que tu dis :

> « Cette URL renvoie 404. Le DNS est bon, Traefik répond, mais aucune règle ne pointe vers une application. C'est exactement ce que notre script va créer. »

### Étape 1 — La commande unique (30 s)

```bash
python3 gandal_deploy.py deploy alice demo landing localhost:5000/landing:v1 80
```

Sortie attendue, dans cet ordre exact :

```
Deploiement de landing dans project-alice-demo
  cree    : project-alice-demo
  cree    : default-limits
  cree    : project-quota
  cree    : isolate-ingress
  cree    : landing
  cree    : landing
  cree    : landing
Succes. Acces : http://landing-demo-alice.16.170.20.250.sslip.io
```

Ce que tu dis, en lisant la sortie :

> « Sept objets. Le namespace d'abord. Puis les valeurs par défaut de ressources. Puis le plafond du projet. Puis l'isolation réseau. Et **seulement ensuite** le Deployment, le Service et l'Ingress — parce que la sécurité doit exister avant l'application, pas après. »

C'est le point pédagogique central : l'ordre dans [`deploy()`](gandal_deploy.py:88) n'est pas cosmétique, c'est une garantie.

### Étape 2 — Les pods apparaissent (45 s)

**Terminal 2** :

```bash
kubectl get pods -n project-alice-demo -w
```

Ce que tu dis pendant l'attente (5 à 15 s) :

> « Kubernetes crée un ReplicaSet, qui demande 2 pods. Le scheduler les place, kubelet demande l'image au registry local, containerd télécharge les couches, puis la readinessProbe teste le port 80 toutes les 5 secondes. Un pod n'est déclaré prêt qu'une fois le port ouvert — pas avant. »

Arrête le `-w` avec `Ctrl+C` quand les deux pods sont `1/1 Running`.

### Étape 3 — Le public ouvre l'URL (45 s)

Sur le navigateur de la salle :

```
http://landing-demo-alice.16.170.20.250.sslip.io
```

Ce que tu dis :

> « Voici le trajet : le DNS encode l'IP dans le nom, donc zéro configuration. Traefik lit l'en-tête `Host`, trouve la règle Ingress, l'envoie au Service, qui répartit sur l'un des deux pods. Rechargez la page plusieurs fois : vous n'atteindrez pas forcément le même pod. »

### Étape 4 — Ce que le script a créé (60 s)

```bash
kubectl get all,ingress,quota,limitrange,networkpolicy -n project-alice-demo
```

Puis les labels, qui sont le cœur du « rattachement à un utilisateur » :

```bash
kubectl get pods -n project-alice-demo --show-labels
```

Ce que tu dis :

> « Chaque pod porte trois labels : `gandal.io/owner=alice`, `gandal.io/project=demo`, `gandal.io/app=landing`. C'est ce qui permet de retrouver les conteneurs d'un utilisateur sans tenir de base de données. Notre commande `list` ne fait rien d'autre : »

```bash
python3 gandal_deploy.py list --user alice
```

### Étape 5 — La résilience (45 s)

```bash
kubectl delete pod -n project-alice-demo -l gandal.io/app=landing
kubectl get pods -n project-alice-demo -w
```

Ce que tu dis :

> « Je détruis les deux pods. Aucun humain n'intervient. Le ReplicaSet constate un écart entre l'état désiré — 2 — et l'état réel — 0, et recrée. La page n'est jamais tombée : pendant la reconstruction, le second pod continue de servir. »

Rafraîchis la page pendant la reconstruction pour le prouver.

### Étape 6 — La mise à jour à chaud (60 s)

```bash
python3 gandal_deploy.py deploy alice demo landing localhost:5000/landing:v2 80
```

Sortie : sept lignes `a jour` — aucune erreur `409 Conflict`, c'est l'idempotence.

```bash
# Le sleep laisse le temps au rolling update de démarrer avant d'observer
sleep 3 && kubectl get pods -n project-alice-demo -w
```

Ce que tu dis :

> « Même commande, nouvelle image. Les ressources existantes sont mises à jour, pas recréées : c'est notre fonction `upsert` qui crée et, si l'objet existe déjà, bascule en `patch`. Les pods sont remplacés un par un — RollingUpdate — donc aucun temps d'arrêt. »

Rafraîchis la page : le titre a changé.

### Étape 7 — Le quota en action (60 s, optionnel)

```bash
kubectl scale deployment landing -n project-alice-demo --replicas=10
sleep 12
kubectl get pods -n project-alice-demo
kubectl get events -n project-alice-demo --field-selector reason=FailedCreate
```

Ce que tu dis :

> « Alice demande 10 réplicas. Kubernetes n'en crée que 4, jamais plus. Les événements expliquent pourquoi : `exceeded quota`. Un utilisateur ne peut pas saturer le cluster des autres, même en le voulant. »

Rétablir immédiatement :

```bash
python3 gandal_deploy.py deploy alice demo landing localhost:5000/landing:v2 80 --replicas 2
```

### Étape 8 — Nettoyage (30 s, optionnel mais marquant)

```bash
python3 gandal_deploy.py delete alice demo --purge
```

Ce que tu dis :

> « Une commande, et le namespace disparaît avec tout ce qu'il contient : pods, service, ingress, quotas, isolation. La suppression d'un namespace est atomique — c'est pour cela que le namespace est l'unité de vie d'un projet. »

Si tu veux finir sur l'image de la page vivante, **ne fais pas cette étape** et garde l'application en ligne pendant les questions.

---

## 4. Répartition du temps

| Segment | Durée | Risque |
|---|---|---|
| État initial + 404 | 1 min | nul |
| `deploy` | 30 s | nul |
| Attente des pods | 1 min | faible |
| Page dans le navigateur | 1 min | **moyen** (réseau de la salle) |
| Inspection des objets et labels | 1,5 min | nul |
| Self-healing | 1 min | faible |
| Mise à jour v1 → v2 | 1,5 min | faible |
| Quota + nettoyage | 1,5 min | nul |

Le seul vrai risque est l'**étape « page dans le navigateur »**. Tout le reste est robuste.

---

## 5. Les cinq pièges à connaître

### Piège 1 — Reconstruire avec le même tag ne change rien

Si tu repousses `landing:v1` après modification, les pods **ne se mettront pas à jour** : `imagePullPolicy` vaut `IfNotPresent` pour un tag qui n'est pas `latest`. Kubernetes ne voit aucun changement dans le manifeste. C'est pourquoi le guide utilise `v2`. En cas d'urgence : `kubectl rollout restart deployment/landing -n project-alice-demo`.

### Piège 2 — Le port 5000 est fermé de l'extérieur

Le registry n'est accessible que depuis la VM ([`registry.yaml`](registry.yaml:39), `hostPort`). Impossible de pousser une image depuis ton PC. Conséquence pratique : **tu ne peux pas corriger l'image cinq minutes avant la démo depuis ton poste.** Il faut SSH vers la VM.

### Piège 3 — `docker` sans `sudo`

Le groupe `docker` ne s'applique qu'après reconnexion ([`install.sh`](install.sh:22)). Dans une session fraîche, soit `sudo docker`, soit `newgrp docker`. Si `sudo docker build` échoue en fin de démo, ne perds pas de temps : ce n'est pas nécessaire, `v1` et `v2` sont déjà poussées.

### Piège 4 — Le nommage est contraint

[`check()`](gandal_deploy.py:32) refuse tout identifiant qui n'est pas en minuscules, chiffres et tirets, ou qui dépasse 20 caractères. `landing` est valide ; `LandingPage` provoquerait un `sys.exit`. Teste tes noms de démo **avant** la présentation.

### Piège 5 — Les quotas peuvent bloquer un déploiement parasite

Les quotas sont par namespace : `project-alice-demo` a son propre plafond, indépendant des autres projets. Mais le nœud peut manquer de mémoire si d'anciens namespaces traînent. Purge-les la veille (étape 1.5).

---

## 6. Plan B, si la démo casse

| Symptôme | Diagnostic | Action immédiate |
|---|---|---|
| L'URL renvoie 404 | L'Ingress n'a pas encore été vu par Traefik | Attendre 5 s, rafraîchir. Sinon `kubectl get ingress -n project-alice-demo` |
| L'URL ne résout pas | DNS de la salle | Basculer sur `curl -H "Host: landing-demo-alice.16.170.20.250.sslip.io" http://16.170.20.250` |
| Pods en `ImagePullBackOff` | Registry ou nom d'image | `kubectl describe pod -n project-alice-demo \| tail -20` |
| Pods en `Pending` | Mémoire ou quota | `kubectl describe pod` → section `Events` |
| `deploy` échoue immédiatement | Kubeconfig | `export KUBECONFIG=$HOME/.kube/config` |
| Cluster injoignable | VM arrêtée | Repasser sur les captures d'écran préparées |

**Prépare toujours une capture d'écran de la page finale et de la sortie du `deploy`.** Si le live échoue, tu montres la preuve et tu continues. Une démo qui échoue proprement avec un plan B est mieux perçue qu'une démo sauvée au forceps.

Un argument de secours redoutablement efficace : le rapport [`VALIDATION_REPORT.md`](VALIDATION_REPORT.md:22) atteste des 9 tests passés. Tu peux dire « la démo vient d'échouer pour une raison réseau, mais voici la campagne de validation complète exécutée sur ce même cluster ».

---

## 7. Variante sans AWS : k3d en local

Si tu crains une coupure réseau ou si l'instance AWS est éteinte, [`NEXT_STEPS.md`](NEXT_STEPS.md:66) décrit une alternative gratuite et hors ligne :

```bash
k3d cluster create gandal-local --port "80:80@loadbalancer"
k3s ctr images import landing-v1.tar     # ou docker save / docker load
export GANDAL_BASE_DOMAIN="gandal.test"
# /etc/hosts : 127.0.0.1 landing-demo-alice.gandal.test
```

Même script, même démonstration, aucun coût, aucune dépendance Internet. C'est une **répétition idéale** : tu peux t'entraîner vingt fois chez toi avant de jouer en salle.

---

## 8. Fichier de séquence, à garder sous les yeux

```bash
# --- Préparation, dans un terminal, avant de parler ---
source ~/gandal-venv/bin/activate
cd ~/gandal-paas
export KUBECONFIG=$HOME/.kube/config
export GANDAL_BASE_DOMAIN="16.170.20.250.sslip.io"

# --- 1. État initial ---
kubectl get ns

# --- 2. Déploiement ---
python3 gandal_deploy.py deploy alice demo landing localhost:5000/landing:v1 80

# --- 3. Pods ---
kubectl get pods -n project-alice-demo -w     # Ctrl+C quand 2x 1/1 Running

# --- 4. Inspection ---
kubectl get all,ingress,quota,limitrange,networkpolicy -n project-alice-demo
kubectl get pods -n project-alice-demo --show-labels
python3 gandal_deploy.py list --user alice

# --- 5. Résilience ---
kubectl delete pod -n project-alice-demo -l gandal.io/app=landing
kubectl get pods -n project-alice-demo -w     # Ctrl+C quand 2x Running

# --- 6. Mise à jour ---
python3 gandal_deploy.py deploy alice demo landing localhost:5000/landing:v2 80
kubectl get pods -n project-alice-demo -w     # observer le rolling update

# --- 7. Quota ---
kubectl scale deployment landing -n project-alice-demo --replicas=10
sleep 12 && kubectl get pods -n project-alice-demo
kubectl get events -n project-alice-demo --field-selector reason=FailedCreate
python3 gandal_deploy.py deploy alice demo landing localhost:5000/landing:v2 80 --replicas 2

# --- 8. Nettoyage, seulement si tu ne veux pas laisser la page en ligne ---
python3 gandal_deploy.py delete alice demo --purge
```

---

## 9. Trois phrases à retenir pour conclure

> « En une commande, on est passé d'un namespace inexistant à une URL publique, avec quotas, isolation réseau, labels de propriété, DNS et deux réplicas résilients. Aucun YAML n'a été écrit à la main. »

> « Ce que vous avez vu est un prototype sur une VM unique : un nœud K3s, plusieurs namespaces. La plateforme GANDAL cible conserve exactement la même architecture logique — seuls l'IP, le domaine, le TLS et le registry sécurisé changent. »

> « Le moteur est prouvé. Reste à le brancher sur le tableau de bord : frontend, authentification, CI/CD — les autres équipes et les phases suivantes de la feuille de route. »

---

## 10. Après la démonstration

Les trois fichiers sont disponibles dans le dépôt :

| Fichier | Contenu |
|---|---|
| [`demo/index.html`](demo/index.html) | La landing page, version `v1` |
| [`demo/Dockerfile`](demo/Dockerfile) | `FROM nginx:alpine` + `COPY` |
| [`scripts/deploy-demo.sh`](scripts/deploy-demo.sh) | Enchaînement automatisé des sections 1 à 8 |

Le script `deploy-demo.sh` accepte trois sous-commandes :

```bash
# La veille : purge, build des deux images, vérification du socle
./scripts/deploy-demo.sh prepare

# En direct : séquence complète (état initial → deploy → pods → ...)
./scripts/deploy-demo.sh run

# Après la démo : suppression du namespace
./scripts/deploy-demo.sh clean
```

La démo est entièrement reproductible depuis le dépôt sans manipulation manuelle.
