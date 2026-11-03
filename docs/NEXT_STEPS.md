# 🚀 Prochaines étapes

Tu es actuellement à la **fin de la Phase 3**. Voici ce qu'il te reste à faire :

## Option 1 : Continuer sur AWS (recommandé pour valider le prototype complet)

### Étape 1 : Déployer Alice (5 minutes)

Depuis AWS CloudShell :

```bash
cd ~/gandal-paas
./scripts/deploy-alice.sh 16.170.20.250
```

**Ce que ça fait :**
- Crée le namespace `project-alice-memoire`
- Déploie 2 réplicas de nginx
- Configure l'Ingress avec Traefik
- Expose sur `http://my-api-memoire-alice.16.170.20.250.sslip.io`

### Étape 2 : Tester l'accès HTTP

```bash
curl http://my-api-memoire-alice.16.170.20.250.sslip.io
```

Tu devrais voir la page d'accueil nginx.

### Étape 3 : Exécuter les tests de validation (10 minutes)

```bash
./scripts/run-validation.sh 16.170.20.250
```

**Les 9 tests vont vérifier :**
1. ✅ Déploiement automatisé (namespace, quotas, NetworkPolicies)
2. ✅ Accès DNS (via sslip.io)
3. ✅ Isolation réseau (Bob ne peut pas accéder aux ressources d'Alice)
4. ✅ Résilience (les pods sont recréés automatiquement)
5. ✅ Quotas (scale up limité par les ResourceQuotas)
6. ✅ Métriques (metrics-server fonctionne)
7. ✅ Identification (labels gandal.io/owner et gandal.io/project)
8. ✅ Idempotence (re-déploiement sans erreur)
9. ✅ Nettoyage (suppression propre avec --purge)

### Étape 4 : Supprimer l'infrastructure AWS

**⚠️ Important : N'oublie pas de détruire les ressources !**

```bash
cd ~/gandal-paas
./scripts/provision-aws.sh down
```

Cela supprime :
- L'instance EC2
- L'Elastic IP
- Le volume EBS
- Le VPC et tous les composants réseau
- Les Security Groups
- La paire de clés

---

## Option 2 : Basculer sur k3d en local (gratuit, plus rapide pour itérer)

Si tu préfères tester localement sans frais AWS :

### Étape 1 : Installer k3d sur ton PC

```bash
# Sur Linux
curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash

# Sur macOS
brew install k3d
```

### Étape 2 : Créer un cluster local

```bash
k3d cluster create gandal-local \
  --port "80:80@loadbalancer" \
  --port "443:443@loadbalancer"
```

### Étape 3 : Adapter la configuration

```bash
export GANDAL_BASE_DOMAIN="gandal.test"
# Ajouter à /etc/hosts : 127.0.0.1 *.gandal.test
```

### Étape 4 : Déployer et tester

Les mêmes commandes `gandal_deploy.py` fonctionnent localement !

---

## 🆘 En cas de problème

### kubectl ne fonctionne pas
```bash
ssh -i ~/gandal ubuntu@16.170.20.250
export KUBECONFIG=$HOME/.kube/config
kubectl get nodes
```

### Les pods ne démarrent pas
```bash
./scripts/ssh-kubectl.sh kubectl describe pod -n project-alice-memoire
./scripts/ssh-kubectl.sh kubectl logs -n project-alice-memoire -l gandal.io/app=my-api
```

### L'URL ne répond pas
```bash
# Vérifier l'Ingress
./scripts/ssh-kubectl.sh kubectl get ingress -n project-alice-memoire

# Vérifier Traefik
./scripts/ssh-kubectl.sh kubectl get pods -n kube-system -l app.kubernetes.io/name=traefik
```

### Problème de résolution DNS (sslip.io)
```bash
# Test depuis la VM
ssh -i ~/gandal ubuntu@16.170.20.250 'curl -v http://my-api-memoire-alice.16.170.20.250.sslip.io'

# Test depuis CloudShell
curl -v http://16.170.20.250
```

---

## 📊 État actuel

✅ **Terminé :**
- Provisionnement AWS
- Installation K3s + registry
- Images publiées

⏳ **En attente :**
- Déploiement Alice
- Tests de validation

🎯 **Objectif final :**
- Valider les 9 tests
- Démontrer le fonctionnement du PaaS
- Documenter pour le passage à XCP-ng

---

## 💡 Recommandation

**Lance maintenant :**

```bash
cd ~/gandal-paas
./scripts/deploy-alice.sh 16.170.20.250
```

Ça prend 2-3 minutes et tu pourras immédiatement voir si tout fonctionne !
