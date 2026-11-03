# État du déploiement GANDAL PaaS

**Date :** 28 octobre 2026  
**IP Elastic :** 16.170.20.250  
**Domaine :** *.16.170.20.250.sslip.io

## ✅ Phases terminées

### Phase 1 : Provisionnement AWS
- ✅ Instance créée : i-0ec13bef707573a48 (eu-north-1a)
- ✅ Elastic IP : 16.170.20.250
- ✅ Security Groups configurés
- ✅ Clé SSH en place

### Phase 2 : Installation du socle
- ✅ K3s installé (v1.36.5+k3s1)
- ✅ Registry privé déployé sur localhost:5000
- ✅ Python venv créé

### Phase 3 : Publication des images
- ✅ Image `localhost:5000/my-api:v1` (nginx:alpine)
- ✅ Image `localhost:5000/curl:latest` (curlimages/curl)
- ✅ Catalogue registry : `{"repositories":["curl","my-api"]}`

## 🔄 Phases en cours

### Phase 4-6 : Déploiement d'Alice

**Action requise depuis CloudShell :**

```bash
cd ~/gandal-paas
./scripts/deploy-alice.sh 16.170.20.250
```

Cette commande va :
1. Déployer l'application `my-api` pour l'utilisateur `alice` dans le projet `memoire`
2. Créer le namespace `project-alice-memoire`
3. Configurer les quotas, NetworkPolicies, et Ingress
4. Exposer l'app sur `http://my-api-memoire-alice.16.170.20.250.sslip.io`

### Phase 7-8 : Tests de validation

**Action requise après le déploiement :**

```bash
./scripts/run-validation.sh 16.170.20.250
```

Cette commande exécute les 9 tests de validation :
1. Déploiement automatisé
2. Accès par DNS
3. Isolation réseau
4. Résilience (self-healing)
5. Respect des quotas
6. Métriques
7. Identification des conteneurs
8. Mise à jour idempotente
9. Nettoyage

## 🔧 Commandes utiles

### Vérifier l'état du cluster
```bash
./scripts/ssh-kubectl.sh kubectl get nodes
./scripts/ssh-kubectl.sh kubectl get pods -A
```

### Se connecter à la VM
```bash
ssh -i ~/gandal ubuntu@16.170.20.250
```

### Vérifier le registry
```bash
ssh -i ~/gandal ubuntu@16.170.20.250 'curl -s http://localhost:5000/v2/_catalog'
```

## ⚠️ Problème résolu

**Symptôme :** `kubectl` ne fonctionnait pas dans les sessions SSH non-interactives  
**Cause :** Conflit entre `/etc/rancher/k3s/k3s.yaml` et `~/.kube/config`  
**Solution :** Export explicite de `KUBECONFIG` dans tous les scripts

## 💰 Rappel coûts AWS

- Instance m7i-flex.large : ~0,09 $/h
- Elastic IP allouée : 0,005 $/h
- Volume gp3 30 Go : ~0,08 $/mois

**Suppression complète après tests :**
```bash
cd ~/gandal-paas
./scripts/provision-aws.sh down
```

## 📚 Documentation

- README principal : `README.md`
- Procédure complète : `simulation_v3.tex` (compiler avec pdflatex)
- Explications : `explication_v3.tex`
