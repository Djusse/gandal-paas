# GANDAL PaaS — Simulation sur AWS

Prototype du socle PaaS GANDAL : une VM unique, K3s, un registry privé et un
script Python qui transforme « un utilisateur + une image » en URL accessible.

L'objectif est de valider la mécanique Kubernetes (Namespaces, quotas,
NetworkPolicies, Ingress, labels de propriété) sans dépendre de l'infrastructure
définitive. Tout est ensuite rejouable sur XCP-ng : seules l'IP, le domaine et
les éléments listés en Phase 9 du document de procédure changent.

## Fichiers

| Fichier | Rôle |
|---|---|
| `install.sh` | Installe Docker, K3s et le registry privé. Autonome et rejouable. |
| `registry.yaml` | Manifeste du registry (déjà inclus dans `install.sh`). |
| `gandal_deploy.py` | Script PaaS : `deploy`, `list`, `status`, `delete`. |
| `simulation_v3.tex` | Procédure d'implémentation (phases 1 à 9). |
| `explication_v3.tex` | Cadrage : périmètre, état final, 9 tests de validation. |
| `tests/validation.sh` | Exécute automatiquement les 9 tests et affiche un bilan. |

## Documentation

```bash
pdflatex simulation_v3.tex && pdflatex simulation_v3.tex
pdflatex explication_v3.tex && pdflatex explication_v3.tex
```

Deux passes sont nécessaires pour la table des matières.

## Phase 1 — Provisionner l'instance AWS

### Option A : script automatique (CloudShell)

Sur votre PC, créer une paire de clés :

```bash
ssh-keygen -t ed25519 -f ~/.ssh/gandal -C gandal-paas
```

Puis dans AWS CloudShell, coller le contenu de `scripts/provision-aws.sh`
(dans l'éditeur CloudShell, ou par copier-coller si le dépôt n'est pas
accessible) et :

```bash
chmod +x provision-aws.sh
./provision-aws.sh up ~/.ssh/gandal.pub
```

Le script crée le VPC, le sous-réseau public, la passerelle Internet, la table
de routage, le Security Group, la paire de clés, l'instance `t3.large` avec
60 Go gp3 et l'Elastic IP, puis affiche l'IP publique. La clé publique doit être
envoyée dans CloudShell (CloudShell n'a pas accès à votre `~/.ssh` local) :

```bash
# Dans CloudShell, creer la cle directement la-bas puis la rapatrier
ssh-keygen -t ed25519 -f ~/gandal -N "" -C gandal-paas
cat ~/gandal          # copier la cle PRIVEE dans ~/.ssh/gandal sur votre PC
./provision-aws.sh up ~/gandal.pub
```

Suppression complète :

```bash
./provision-aws.sh down
```

### Option B : console AWS à la main

| Élément | Valeur |
|---|---|
| AMI | Ubuntu 24.04 LTS |
| Type | `t3.large` (2 vCPU, 8 Go) |
| Disque racine | 60 Go gp3 |
| IP | Elastic IP (obligatoire pour le DNS) |
| VPC | `10.0.0.0/16` avec sous-réseau public |

Security Group :

| Port | Source | Usage |
|---|---|---|
| 22 | votre IP | SSH |
| 80 | 0.0.0.0/0 | HTTP (Ingress Traefik) |
| 443 | 0.0.0.0/0 | HTTPS (non utilisé en simulation, prévu) |
| 6443 | votre IP | API Kubernetes, seulement pour piloter depuis le PC |

Le port **5000 n'est pas ouvert** : le registry n'est pas exposé à Internet.
Les images sont construites et poussées depuis la VM.

> L'Elastic IP et le volume gp3 sont facturés même instance arrêtée.
> Supprimer toutes les ressources après la démonstration.

## Phase 2 — Installer le socle

```bash
scp install.sh ubuntu@<ELASTIC_IP>:~/
ssh ubuntu@<ELASTIC_IP>
chmod +x install.sh
./install.sh <ELASTIC_IP>
```

Le script est rejouable : le relancer ne casse rien. Il vérifie lui-même que
l'API Kubernetes répond et que le registry sert sur `localhost:5000`.

Vérification :

```bash
kubectl get nodes          # Ready
kubectl get pods -A        # traefik, coredns, metrics-server en Running
curl http://localhost:5000/v2/_catalog
```

## Phase 3 — Publier une image de test

Le groupe `docker` ne s'applique qu'après reconnexion : utiliser `sudo docker`
ou `newgrp docker` dans la session courante.

```bash
sudo docker pull nginx:alpine
sudo docker tag nginx:alpine localhost:5000/my-api:v1
sudo docker push localhost:5000/my-api:v1

# Sonde réseau pour le test d'isolation
sudo docker pull curlimages/curl:latest
sudo docker tag curlimages/curl:latest localhost:5000/curl:latest
sudo docker push localhost:5000/curl:latest
```

## Phase 4-6 — Déployer une application

```bash
source ~/gandal-venv/bin/activate
export GANDAL_BASE_DOMAIN="<ELASTIC_IP>.sslip.io"

python gandal_deploy.py deploy alice memoire my-api localhost:5000/my-api:v1 80
```

Le script crée le namespace, le LimitRange, le ResourceQuota, la NetworkPolicy,
le Deployment, le Service et l'Ingress, puis affiche l'URL.

Nommage : `project-<user>-<projet>` pour le namespace,
`<app>-<projet>-<user>.<domaine>` pour l'URL.

## Phase 7-8 — Valider

```bash
./tests/validation.sh alice memoire my-api
```

Le script exécute les 9 tests de réussite et affiche un bilan. Il attend un
environnement préparé (Phase 2 à 4) et `GANDAL_BASE_DOMAIN` défini.

## Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `GANDAL_BASE_DOMAIN` | `gandal.test` | Domaine de base des URL |
| `GANDAL_INGRESS_CLASS` | `traefik` | Classe d'Ingress |
| `GANDAL_REPLICAS` | `2` | Réplicas par défaut |
| `GANDAL_QUOTA_REQ_CPU` | `1` | Quota : requests CPU |
| `GANDAL_QUOTA_REQ_MEM` | `1Gi` | Quota : requests mémoire |
| `GANDAL_QUOTA_LIM_CPU` | `2` | Quota : limits CPU |
| `GANDAL_QUOTA_LIM_MEM` | `2Gi` | Quota : limits mémoire |
| `GANDAL_QUOTA_PODS` | `4` | Quota : nombre de pods |

## Passage à XCP-ng

Ce qui ne change pas : `install.sh`, `registry.yaml`, la logique du script
Python, les manifests générés, les labels, les quotas, les NetworkPolicies.

Ce qui change :

| Élément | AWS | GANDAL (XCP-ng) |
|---|---|---|
| Adresse d'entrée | Elastic IP | IP fournie par Système/Réseau |
| Domaine | sslip.io ou `gandal.test` | Domaine GANDAL + wildcard Réseau |
| TLS | absent | cert-manager ou certificats fournis |
| Registry | HTTP sans authentification | TLS + authentification |
| Pare-feu | Security Group | Règles Réseau/Sécurité |
| Accès Internet sortant | libre | à vérifier, sinon installation hors ligne |
| IP du certificat | `--tls-san` | ajouter l'IP dans `config.yaml` puis redémarrer K3s |

Si le réseau est isolé : `docker save` / `docker load` pour les images et
installation hors ligne de K3s.
