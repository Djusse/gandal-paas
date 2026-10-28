#!/usr/bin/env python3
"""GANDAL PaaS (simulation) : deploy / list / status / delete.

Variables d'environnement :
  GANDAL_BASE_DOMAIN    domaine de base (defaut : gandal.test)
  GANDAL_INGRESS_CLASS  classe d'Ingress (defaut : traefik)
  GANDAL_REPLICAS       nombre de replicas par defaut (defaut : 2)
  GANDAL_QUOTA_REQ_CPU, GANDAL_QUOTA_REQ_MEM, GANDAL_QUOTA_LIM_CPU,
  GANDAL_QUOTA_LIM_MEM, GANDAL_QUOTA_PODS
"""
import argparse
import os
import re
import sys

from kubernetes import client, config
from kubernetes.client.rest import ApiException

BASE_DOMAIN = os.getenv("GANDAL_BASE_DOMAIN", "gandal.test")
INGRESS_CLASS = os.getenv("GANDAL_INGRESS_CLASS", "traefik")
REPLICAS = int(os.getenv("GANDAL_REPLICAS", "2"))
QUOTA = {
    "requests.cpu": os.getenv("GANDAL_QUOTA_REQ_CPU", "1"),
    "requests.memory": os.getenv("GANDAL_QUOTA_REQ_MEM", "1Gi"),
    "limits.cpu": os.getenv("GANDAL_QUOTA_LIM_CPU", "2"),
    "limits.memory": os.getenv("GANDAL_QUOTA_LIM_MEM", "2Gi"),
    "pods": os.getenv("GANDAL_QUOTA_PODS", "4"),
}
NAME_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")


def check(label, value):
    if not NAME_RE.match(value) or len(value) > 20:
        sys.exit(f"{label} invalide '{value}' : minuscules, chiffres, "
                 "tirets, 20 caracteres max")


def ns_of(user, project):
    return f"project-{user}-{project}"


def host_of(user, project, app):
    return f"{app}-{project}-{user}.{BASE_DOMAIN}"


def labels(user, project, app=None):
    d = {"gandal.io/owner": user, "gandal.io/project": project}
    if app:
        d["gandal.io/app"] = app
    return d


def load_config():
    """Charge le kubeconfig, avec un message clair s'il est absent."""
    try:
        config.load_kube_config()
    except Exception as exc:  # ConfigException et variantes
        sys.exit(f"ERREUR : kubeconfig introuvable ou invalide ({exc}).\n"
                 "  Sur la VM : export KUBECONFIG=$HOME/.kube/config\n"
                 "  Depuis un PC : copier ~/.kube/config et remplacer\n"
                 "  127.0.0.1 par l'IP publique dans le champ 'server'.")


def upsert(create, patch, name, body):
    """Cree la ressource ; si elle existe deja (409), la met a jour."""
    try:
        create(body)
        print(f"  cree    : {name}")
    except ApiException as e:
        if e.status != 409:
            raise
        patch(name, body)
        print(f"  a jour  : {name}")


def deploy(a):
    for label, value in (("user", a.user), ("projet", a.project),
                         ("app", a.app)):
        check(label, value)
    load_config()
    v1, apps, net = (client.CoreV1Api(), client.AppsV1Api(),
                     client.NetworkingV1Api())
    ns = ns_of(a.user, a.project)
    lab = labels(a.user, a.project, a.app)
    print(f"Deploiement de {a.app} dans {ns}")

    # 1. Namespace (porte owner et project)
    upsert(v1.create_namespace, lambda n, b: v1.patch_namespace(n, b), ns,
           {"metadata": {"name": ns, "labels": labels(a.user, a.project)}})

    # 2. LimitRange : valeurs par defaut des conteneurs
    upsert(lambda b: v1.create_namespaced_limit_range(ns, b),
           lambda n, b: v1.patch_namespaced_limit_range(n, ns, b),
           "default-limits",
           {"metadata": {"name": "default-limits"},
            "spec": {"limits": [{
                "type": "Container",
                "default": {"cpu": "500m", "memory": "512Mi"},
                "defaultRequest": {"cpu": "100m", "memory": "128Mi"}}]}})

    # 3. ResourceQuota : plafond du projet
    upsert(lambda b: v1.create_namespaced_resource_quota(ns, b),
           lambda n, b: v1.patch_namespaced_resource_quota(n, ns, b),
           "project-quota",
           {"metadata": {"name": "project-quota"}, "spec": {"hard": QUOTA}})

    # 4. NetworkPolicy : meme namespace + kube-system (Traefik)
    upsert(lambda b: net.create_namespaced_network_policy(ns, b),
           lambda n, b: net.patch_namespaced_network_policy(n, ns, b),
           "isolate-ingress",
           {"metadata": {"name": "isolate-ingress"},
            "spec": {"podSelector": {}, "policyTypes": ["Ingress"],
                     "ingress": [
                         {"from": [{"podSelector": {}}]},
                         {"from": [{"namespaceSelector": {"matchLabels": {
                             "kubernetes.io/metadata.name":
                                 "kube-system"}}}]}]}})

    # 5. Deployment (labels de propriete sur les pods)
    probe = {"tcpSocket": {"port": a.port}, "periodSeconds": 5}
    upsert(lambda b: apps.create_namespaced_deployment(ns, b),
           lambda n, b: apps.patch_namespaced_deployment(n, ns, b),
           a.app,
           {"metadata": {"name": a.app, "labels": lab},
            "spec": {
                "replicas": a.replicas,
                "selector": {"matchLabels": {"gandal.io/app": a.app}},
                "template": {
                    "metadata": {"labels": lab},
                    "spec": {"containers": [{
                        "name": a.app, "image": a.image,
                        "ports": [{"containerPort": a.port}],
                        "readinessProbe": dict(probe,
                                               initialDelaySeconds=3),
                        "livenessProbe": dict(probe,
                                              initialDelaySeconds=10),
                        "resources": {
                            "requests": {"cpu": "100m",
                                         "memory": "128Mi"},
                            "limits": {"cpu": "500m",
                                       "memory": "512Mi"}}}]}}}})

    # 6. Service (nom stable a l'interieur du cluster)
    upsert(lambda b: v1.create_namespaced_service(ns, b),
           lambda n, b: v1.patch_namespaced_service(n, ns, b),
           a.app,
           {"metadata": {"name": a.app, "labels": lab},
            "spec": {"selector": {"gandal.io/app": a.app},
                     "ports": [{"port": 80, "targetPort": a.port}]}})

    # 7. Ingress (nom DNS externe)
    host = host_of(a.user, a.project, a.app)
    upsert(lambda b: net.create_namespaced_ingress(ns, b),
           lambda n, b: net.patch_namespaced_ingress(n, ns, b),
           a.app,
           {"metadata": {"name": a.app, "labels": lab},
            "spec": {"ingressClassName": INGRESS_CLASS,
                     "rules": [{"host": host, "http": {"paths": [{
                         "path": "/", "pathType": "Prefix",
                         "backend": {"service": {
                             "name": a.app,
                             "port": {"number": 80}}}}]}}]}})

    print(f"Succes. Acces : http://{host}")


def list_pods(a):
    load_config()
    v1 = client.CoreV1Api()
    sel = f"gandal.io/owner={a.user}" if a.user else "gandal.io/owner"
    pods = v1.list_pod_for_all_namespaces(label_selector=sel).items
    print(f"{'OWNER':12}{'PROJECT':14}{'APP':16}{'POD':40}"
          f"{'STATUS':10}IP")
    for p in pods:
        lb = p.metadata.labels or {}
        print(f"{lb.get('gandal.io/owner', ''):12}"
              f"{lb.get('gandal.io/project', ''):14}"
              f"{lb.get('gandal.io/app', ''):16}"
              f"{p.metadata.name:40}{p.status.phase:10}"
              f"{p.status.pod_ip or '-'}")


def status(a):
    load_config()
    v1, apps = client.CoreV1Api(), client.AppsV1Api()
    ns = ns_of(a.user, a.project)
    try:
        d = apps.read_namespaced_deployment(a.app, ns)
    except ApiException as e:
        if e.status == 404:
            sys.exit(f"ERREUR : l'application '{a.app}' n'existe pas dans "
                     f"'{ns}' (ou le projet n'a jamais ete deploye).\n"
                     f"  Verifier avec : python {sys.argv[0]} list")
        raise
    print(f"Replicas prets : {d.status.ready_replicas or 0}/{d.spec.replicas}")
    print(f"URL            : http://{host_of(a.user, a.project, a.app)}")
    pods = v1.list_namespaced_pod(
        ns, label_selector=f"gandal.io/app={a.app}").items
    for p in pods:
        print(f"Pod {p.metadata.name} : {p.status.phase}, "
              f"IP {p.status.pod_ip}")


def delete(a):
    load_config()
    v1, apps, net = (client.CoreV1Api(), client.AppsV1Api(),
                     client.NetworkingV1Api())
    ns = ns_of(a.user, a.project)
    if a.purge:
        try:
            v1.delete_namespace(ns)
        except ApiException as e:
            if e.status == 404:
                sys.exit(f"ERREUR : le projet '{ns}' n'existe pas.")
            raise
        print(f"Projet {ns} supprime "
              "(namespace, quotas, isolation et toutes ses applications)")
        return
    if not a.app:
        sys.exit("indiquer l'application, ou utiliser --purge")
    # Note : sans --purge, le namespace, le LimitRange, le ResourceQuota et la
    # NetworkPolicy sont conserves (le projet survit a la suppression d'une app).
    for fn in (lambda: net.delete_namespaced_ingress(a.app, ns),
               lambda: v1.delete_namespaced_service(a.app, ns),
               lambda: apps.delete_namespaced_deployment(a.app, ns)):
        try:
            fn()
        except ApiException as e:
            if e.status != 404:
                raise
    print(f"Application {a.app} supprimee "
          f"(projet {ns} conserve ; --purge pour tout supprimer)")


def main():
    p = argparse.ArgumentParser(description="GANDAL PaaS (simulation)")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("deploy", help="creer ou mettre a jour une application")
    for n in ("user", "project", "app", "image"):
        d.add_argument(n)
    d.add_argument("port", type=int)
    d.add_argument("--replicas", type=int, default=REPLICAS)
    d.set_defaults(fn=deploy)

    ls = sub.add_parser("list", help="lister les pods avec proprietaire et IP")
    ls.add_argument("--user")
    ls.set_defaults(fn=list_pods)

    s = sub.add_parser("status", help="etat d'une application")
    for n in ("user", "project", "app"):
        s.add_argument(n)
    s.set_defaults(fn=status)

    x = sub.add_parser("delete", help="supprimer une application ou un projet")
    x.add_argument("user")
    x.add_argument("project")
    x.add_argument("app", nargs="?")
    x.add_argument("--purge", action="store_true")
    x.set_defaults(fn=delete)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
