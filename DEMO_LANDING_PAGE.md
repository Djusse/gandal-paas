# Guide — Déploiement en direct d'une landing page

> Document de préparation à une démonstration live du prototype GANDAL PaaS.
> Public visé : camarades de promotion, jury, équipe projet.
> Durée du live : **6 à 8 minutes**. Durée de préparation : **10 minutes**.

---

## Ce que la démo doit prouver

En 6 à 8 minutes, l'audience doit voir trois choses qu'aucune slide ne peut montrer :

1. **Du vide au public** : un namespace inexistant devient une URL visitable en une commande.
2. **Aucune intervention manuelle** : ni YAML écrit à la main, ni `kubectl apply`. Tout passe par `gandal_deploy.py`.
3. **Le PaaS, pas seulement Kubernetes** : quotas, isolation et labels sont créés *avant* l'application, par le même appel.

### Pourquoi `nginxdemos/hello` ?

L'image [nginxdemos/hello](https://hub.docker.com/r/nginxdemos/hello) est une image officielle NGINX disponible directement sur Docker Hub. Elle affiche une page avec le **hostname du pod, son IP et le port** — ce qui prouve visuellement le load balancing sans rien expliquer : en rechargeant la page plusieurs fois, le hostname change entre les deux réplicas.

- ✅ Zéro build, zéro Dockerfile, zéro fichier à créer
- ✅ La page change à chaque rechargement (hostname du pod visible)
- ✅ Image publique maintenue par NGINX Inc.
- ✅ Pour la v2 : `nginxdemos/hello:plain-text` retourne du texte brut — suffisant pour montrer que la mise à jour a eu lieu

Le principe de la démo : **tout ce qui est risqué se prépare avant ; en direct, on ne fait que la commande `deploy` et des observations.**

---

## 1. Préparation (la veille, 10 min)

### 1.1 Se connecter à la VM

```bash
ssh -i ~/gandal ubuntu@16.170.20.250
```

### 1.2 Tirer et pousser les deux images dans le registry local

Pas de build nécessaire. On tire directement depuis Docker Hub et on retague vers le registry local.

```bash
export KUBECONFIG=$HOME/.kube/config

# Version 1 : page HTML avec hostname, IP, port
sudo docker pull nginxdemos/hello
sudo docker tag nginxdemos/hello localhost:5000/landing:v1
sudo docker push localhost:5000/landing:v1

# Version 2 : réponse texte brut (différence visible immédiatement)
sudo docker pull nginxdemos/hello:plain-text
sudo docker tag nginxdemos/hello:plain-text localhost:5000/landing:v2
sudo docker push localhost:5000/landing:v2

# Vérification : les deux tags doivent apparaître
curl -s http://localhost:5000/v2/landing/tags/list
```

Résultat attendu : `{"name":"landing","tags":["v1","v2"]}`.

### 1.3 Vérifier que le socle est sain

```bash
kubectl get nodes
kubectl get pods -A | grep -E 'traefik|coredns|metrics|registry'
kubectl -n gandal-system get deploy private-registry
```

Résultat attendu : tout en `Running`, registry en `1/1`.

### 1.4 Purger les namespaces précédents

La démo doit partir d'un état propre.

```bash
export KUBECONFIG=$HOME/.kube/config

python3 ~/gandal-paas/gandal_deploy.py delete alice demo --purge 2>/dev/null || true
python3 ~/gandal-paas/gandal_deploy.py delete alice memoire --purge 2>/dev/null || true
python3 ~/gandal-paas/gandal_deploy.py delete bob test --purge 2>/dev/null || true

kubectl get ns
```

Résultat attendu : seuls les namespaces système (`default`, `kube-system`, `kube-public`, `kube-node-lease`, `gandal-system`).

### 1.5 Pré-chauffer le DNS

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://landing-demo-alice.16.170.20.250.sslip.io
```

Un `404` prouve que sslip.io résout déjà et que Traefik répond. C'est un excellent point à montrer en live juste avant le `deploy`.

---

## 2. Checklist T-30 minutes

| Point | Commande de contrôle | Attendu |
|---|---|---|
| VM joignable | `ssh -i ~/gandal ubuntu@16.170.20.250 'uptime'` | réponse |
| Images présentes | `ssh -i ~/gandal ubuntu@16.170.20.250 'curl -s localhost:5000/v2/landing/tags/list'` | `v1`, `v2` |
| Cluster sain | `kubectl get nodes` | `Ready` |
| Namespace absent | `kubectl get ns \| grep project` | rien |
| DNS résout | `curl -s -o /dev/null -w '%{http_code}\n' http://landing-demo-alice.16.170.20.250.sslip.io` | `404` |
| Navigateur de la salle | ouvrir l'URL ci-dessus | page Traefik 404 |
| Terminal lisible | police ≥ 18 pt, fond sombre | — |

> **Point le plus important** : teste le navigateur depuis le réseau de la salle avant de commencer. Certains établissements bloquent sslip.io ou le port 80 sortant. Si c'est le cas, voir section 6 (Plan B).

---

## 3. Déroulé en direct — 7 minutes

### Étape 0 — Initialisation (30 s)

Sur la VM :

```bash
source ~/gandal-venv/bin/activate
cd ~/gandal-paas
export KUBECONFIG=$HOME/.kube/config
export GANDAL_BASE_DOMAIN="16.170.20.250.sslip.io"
```

Montrer l'état vide :

```bash
kubectl get ns
```

Montrer le 404 :

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://landing-demo-alice.16.170.20.250.sslip.io
```

> « Cette URL renvoie 404. Le DNS est bon, Traefik répond, mais aucune règle n'existe encore. C'est ce que notre script va créer. »

### Étape 1 — La commande unique (30 s)

```bash
python3 gandal_deploy.py deploy alice demo landing localhost:5000/landing:v1 80
```

Sortie attendue :

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

> « Sept objets. Namespace, limites, quota, isolation réseau — dans cet ordre. La sécurité est posée *avant* l'application, pas après. »

### Étape 2 — Les pods apparaissent (45 s)

```bash
kubectl get pods -n project-alice-demo -w
```

> « Kubernetes crée un ReplicaSet qui demande 2 pods. Le scheduler les place, kubelet tire l'image depuis le registry local, containerd démarre le conteneur, puis la readinessProbe vérifie le port 80. Le pod n'est Ready qu'une fois le port ouvert. »

`Ctrl+C` quand les deux pods sont `1/1 Running`.

### Étape 3 — Le public ouvre l'URL (60 s)

Ouvrir dans le navigateur de la salle :

```
http://landing-demo-alice.16.170.20.250.sslip.io
```

La page affiche le **hostname du pod**, son IP et le port.

> « Rechargez plusieurs fois. Le hostname change : `landing-xxx1`, puis `landing-xxx2`. C'est le Service Kubernetes qui répartit la charge en round-robin entre les deux réplicas. »

### Étape 4 — Inspection des objets créés (60 s)

```bash
kubectl get all,ingress,quota,limitrange,networkpolicy -n project-alice-demo
```

```bash
kubectl get pods -n project-alice-demo --show-labels
```

> « Chaque pod porte trois labels : `gandal.io/owner=alice`, `gandal.io/project=demo`, `gandal.io/app=landing`. C'est ce qui permet de retrouver les conteneurs d'un utilisateur sans base de données. »

```bash
python3 gandal_deploy.py list --user alice
```

### Étape 5 — Résilience (45 s)

```bash
kubectl delete pod -n project-alice-demo -l gandal.io/app=landing
kubectl get pods -n project-alice-demo -w
```

> « Je détruis les deux pods. Le ReplicaSet constate l'écart entre l'état désiré (2) et réel (0) et recrée immédiatement. Pendant la reconstruction, la page reste accessible depuis les nouveaux pods. »

Rafraîchir la page pendant la reconstruction pour le montrer.

`Ctrl+C` quand les deux pods sont de nouveau `1/1 Running`.

### Étape 6 — Mise à jour à chaud (60 s)

```bash
python3 gandal_deploy.py deploy alice demo landing localhost:5000/landing:v2 80
```

Sortie : sept lignes `a jour` — zéro erreur, c'est l'idempotence.

```bash
sleep 3 && kubectl get pods -n project-alice-demo -w
```

> « Même commande, nouvelle image. La fonction `upsert` bascule en `patch` si l'objet existe déjà. Les pods sont remplacés un par un — RollingUpdate — zéro interruption de service. »

Rafraîchir la page : la réponse est maintenant en texte brut (v2 plain-text).

`Ctrl+C` quand les nouveaux pods sont `1/1 Running`.

### Étape 7 — Quotas en action (60 s, optionnel)

```bash
kubectl scale deployment landing -n project-alice-demo --replicas=10
sleep 12
kubectl get pods -n project-alice-demo
kubectl get events -n project-alice-demo --field-selector reason=FailedCreate
```

> « Alice demande 10 réplicas. Kubernetes n'en crée que 4. Les événements expliquent : `exceeded quota`. Un utilisateur ne peut pas saturer le cluster. »

Rétablir :

```bash
python3 gandal_deploy.py deploy alice demo landing localhost:5000/landing:v2 80 --replicas 2
```

### Étape 8 — Nettoyage (30 s, optionnel)

```bash
python3 gandal_deploy.py delete alice demo --purge
```

> « Une commande, et le namespace disparaît avec tout ce qu'il contient. La suppression est atomique — c'est pour ça que le namespace est l'unité de vie d'un projet. »

Si tu veux laisser la page en ligne pendant les questions, **saute cette étape**.

---

## 4. Répartition du temps

| Segment | Durée | Risque |
|---|---|---|
| Initialisation + 404 | 1 min | nul |
| `deploy` | 30 s | nul |
| Attente des pods | 1 min | faible |
| Page dans le navigateur | 1 min | **moyen** (réseau de la salle) |
| Inspection des objets | 1 min | nul |
| Résilience | 1 min | faible |
| Mise à jour v1 → v2 | 1,5 min | faible |
| Quota + nettoyage | 1 min | nul |

---

## 5. Les pièges à connaître

### Piège 1 — Réutiliser un tag ne met pas à jour les pods

Si tu repousses `landing:v1` après modification, les pods **ne se mettront pas à jour** : `imagePullPolicy` vaut `IfNotPresent` pour un tag fixe. C'est pourquoi la démo utilise deux tags distincts (`v1` et `v2`). En cas d'urgence : `kubectl rollout restart deployment/landing -n project-alice-demo`.

### Piège 2 — Le port 5000 est fermé depuis l'extérieur

Le registry n'est accessible que depuis la VM (`hostPort 5000`). **Impossible de pousser depuis ton PC.** Toute correction d'image doit se faire en SSH sur la VM.

### Piège 3 — `docker` sans `sudo`

Le groupe `docker` ne s'applique qu'après reconnexion SSH. Dans une session fraîche, utilise `sudo docker` ou `newgrp docker`. Pour la démo, les images sont déjà poussées — `sudo docker` n'est plus nécessaire.

### Piège 4 — Le nommage est contraint

`gandal_deploy.py` refuse tout identifiant non conforme (majuscules, caractères spéciaux, plus de 20 caractères). `landing`, `alice`, `demo` sont tous valides. Teste tes noms **avant** la présentation.

### Piège 5 — Anciens namespaces qui traînent

Les quotas sont par namespace, mais la mémoire du nœud est partagée. Des namespaces non purgés (notamment `project-alice-memoire` et `project-bob-test` du test de validation) consomment de la RAM. L'étape 1.4 est là pour ça.

---

## 6. Plan B si la démo casse

| Symptôme | Cause probable | Action |
|---|---|---|
| URL renvoie 404 | Traefik n'a pas encore vu l'Ingress | Attendre 5 s, rafraîchir. Vérifier : `kubectl get ingress -n project-alice-demo` |
| URL ne résout pas | DNS de la salle bloqué | `curl -H "Host: landing-demo-alice.16.170.20.250.sslip.io" http://16.170.20.250` |
| Pods en `ImagePullBackOff` | Nom d'image incorrect | `kubectl describe pod -n project-alice-demo \| grep -A5 Events` |
| Pods en `Pending` | Mémoire insuffisante | Purger les autres namespaces, puis `kubectl describe pod` |
| `deploy` échoue | Kubeconfig absent | `export KUBECONFIG=$HOME/.kube/config` |
| VM injoignable | Instance arrêtée | Montrer les captures d'écran préparées + `VALIDATION_REPORT.md` |

**Prépare toujours une capture d'écran de la page et de la sortie du `deploy`.** `VALIDATION_REPORT.md` atteste des 9 tests passés et constitue une preuve solide même si le live échoue.

---

## 7. Variante sans AWS : k3d en local

Si l'instance AWS est éteinte ou si le réseau de la salle pose problème :

```bash
# Sur ton PC
k3d cluster create gandal-local --port "80:80@loadbalancer"
export KUBECONFIG=$(k3d kubeconfig write gandal-local)

# Charger l'image localement (sans registry)
docker pull nginxdemos/hello
k3d image import nginxdemos/hello -c gandal-local

export GANDAL_BASE_DOMAIN="gandal.test"
# Ajouter dans /etc/hosts : 127.0.0.1 landing-demo-alice.gandal.test

source ~/gandal-venv/bin/activate
python3 gandal_deploy.py deploy alice demo landing nginxdemos/hello 80
```

Même script, même démonstration, zéro coût, zéro dépendance Internet. C'est la répétition idéale.

---

## 8. Séquence complète — à garder sous les yeux

```bash
# --- Initialisation ---
source ~/gandal-venv/bin/activate
cd ~/gandal-paas
export KUBECONFIG=$HOME/.kube/config
export GANDAL_BASE_DOMAIN="16.170.20.250.sslip.io"

# --- 0. Etat initial ---
kubectl get ns
curl -s -o /dev/null -w '%{http_code}\n' http://landing-demo-alice.16.170.20.250.sslip.io

# --- 1. Deploiement ---
python3 gandal_deploy.py deploy alice demo landing localhost:5000/landing:v1 80

# --- 2. Pods ---
kubectl get pods -n project-alice-demo -w
# Ctrl+C quand 2x 1/1 Running

# --- 3. URL ---
# Ouvrir http://landing-demo-alice.16.170.20.250.sslip.io dans le navigateur
# Recharger plusieurs fois : hostname change entre les deux pods

# --- 4. Inspection ---
kubectl get all,ingress,quota,limitrange,networkpolicy -n project-alice-demo
kubectl get pods -n project-alice-demo --show-labels
python3 gandal_deploy.py list --user alice

# --- 5. Resilience ---
kubectl delete pod -n project-alice-demo -l gandal.io/app=landing
kubectl get pods -n project-alice-demo -w
# Ctrl+C quand 2x Running

# --- 6. Mise a jour v1 -> v2 ---
python3 gandal_deploy.py deploy alice demo landing localhost:5000/landing:v2 80
sleep 3 && kubectl get pods -n project-alice-demo -w
# Ctrl+C quand les nouveaux pods sont Running
# Recharger le navigateur : reponse en texte brut (v2)

# --- 7. Quota ---
kubectl scale deployment landing -n project-alice-demo --replicas=10
sleep 12 && kubectl get pods -n project-alice-demo
kubectl get events -n project-alice-demo --field-selector reason=FailedCreate
python3 gandal_deploy.py deploy alice demo landing localhost:5000/landing:v2 80 --replicas 2

# --- 8. Nettoyage (optionnel) ---
python3 gandal_deploy.py delete alice demo --purge
```

---

## 9. Trois phrases pour conclure

> « En une commande, on est passé d'un namespace inexistant à une URL publique, avec quotas, isolation réseau, labels de propriété, DNS et deux réplicas résilients. Aucun YAML n'a été écrit à la main. »

> « Ce que vous avez vu tourne sur une VM unique. La plateforme GANDAL cible conserve exactement la même architecture logique — seuls l'IP, le domaine, le TLS et le registry sécurisé changent. »

> « Le moteur est prouvé. Reste à le brancher sur le tableau de bord : frontend, authentification, CI/CD — les phases suivantes de la feuille de route. »
