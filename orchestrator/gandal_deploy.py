#!/usr/bin/env python3
"""CLI GANDAL PaaS : deploy / list / status / delete.

Couche fine au-dessus de :mod:`gandal.k8s`. La convention de nommage reste
celle du backend (D3) : namespace ``proj-{projet}`` et URL
``{projet}.{GANDAL_BASE_DOMAIN}``. Le nom d'utilisateur n'intervient que dans
les labels, et il est normalisé.

Variables d'environnement :
  GANDAL_BASE_DOMAIN      domaine de base (défaut : gandal.test)
  GANDAL_INGRESS_CLASS    classe d'Ingress (défaut : traefik)
  GANDAL_REPLICAS         réplicas par défaut (défaut : 2)
  GANDAL_QUOTA_REQ_CPU, GANDAL_QUOTA_REQ_MEM, GANDAL_QUOTA_LIM_CPU,
  GANDAL_QUOTA_LIM_MEM, GANDAL_QUOTA_PODS
  KUBECONFIG              chemin du kubeconfig (si hors cluster)
"""

from __future__ import annotations

import argparse
import sys

from gandal.config import settings
from gandal.k8s import (
    APP_LABEL,
    OWNER_LABEL,
    PROJECT_LABEL,
    DeploySpec,
    InvalidDeployment,
    KubernetesBackend,
    namespace_for,
)
from gandal.names import validate_name


def _backend() -> KubernetesBackend:
    try:
        return KubernetesBackend.from_environment(settings)
    except Exception as exc:  # kubeconfig absent ou invalide
        sys.exit(
            f"ERREUR : client Kubernetes indisponible ({exc}).\n"
            "  Sur la VM : export KUBECONFIG=$HOME/.kube/config\n"
            "  Depuis un PC : copier ~/.kube/config et remplacer\n"
            "  127.0.0.1 par l'IP publique dans le champ 'server'."
        )


def cmd_deploy(args: argparse.Namespace) -> int:
    try:
        validate_name(args.project, "projet")
        spec = DeploySpec(
            deployment_id=args.deployment_id,
            project=args.project,
            owner=args.user,
            namespace=namespace_for(args.project),
            image=args.image,
            port=args.port,
            tag=args.tag,
            digest=args.digest,
            replicas=args.replicas,
        )
    except InvalidDeployment as exc:
        sys.exit(f"ERREUR : {exc}")

    backend = _backend()
    print(f"Déploiement de {spec.app} dans {spec.namespace}")
    url = backend.apply(spec)
    print(f"Succès. Accès : {url}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    backend = _backend()
    selector = f"{OWNER_LABEL}={args.user}" if args.user else OWNER_LABEL
    pods = backend.core.list_pod_for_all_namespaces(label_selector=selector).items
    print(f"{'OWNER':14}{'PROJECT':18}{'APP':18}{'POD':42}{'STATUS':10}IP")
    for pod in pods:
        labels = pod.metadata.labels or {}
        print(
            f"{labels.get(OWNER_LABEL, ''):14}"
            f"{labels.get(PROJECT_LABEL, ''):18}"
            f"{labels.get(APP_LABEL, ''):18}"
            f"{pod.metadata.name:42}{pod.status.phase:10}"
            f"{pod.status.pod_ip or '-'}"
        )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    backend = _backend()
    namespace = namespace_for(args.project)
    try:
        deployment = backend.apps.read_namespaced_deployment(args.app, namespace)
    except Exception as exc:  # ApiException 404 et variantes
        sys.exit(
            f"ERREUR : l'application '{args.app}' n'existe pas dans "
            f"'{namespace}' ({exc}).\n"
            f"  Vérifier avec : python {sys.argv[0]} list"
        )

    desired = deployment.spec.replicas or 0
    ready = deployment.status.ready_replicas or 0
    print(f"Réplicas prêts : {ready}/{desired}")
    print(f"URL            : http://{args.project}.{settings.base_domain}")
    pods = backend.core.list_namespaced_pod(
        namespace, label_selector=f"{APP_LABEL}={args.app}"
    ).items
    for pod in pods:
        print(f"Pod {pod.metadata.name} : {pod.status.phase}, IP {pod.status.pod_ip}")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    backend = _backend()
    namespace = namespace_for(args.project)

    if args.purge:
        try:
            backend.delete_namespace(namespace)
        except InvalidDeployment as exc:
            sys.exit(f"ERREUR : {exc}")
        print(
            f"Projet {namespace} supprimé "
            "(namespace, quotas, isolation et toutes ses applications)"
        )
        return 0

    if not args.app:
        sys.exit("indiquer l'application, ou utiliser --purge")

    from kubernetes.client.rest import ApiException

    # Sans --purge, le namespace, le LimitRange, le ResourceQuota et la
    # NetworkPolicy sont conservés (le projet survit à la suppression d'une app).
    operations = (
        lambda: backend.networking.delete_namespaced_ingress(args.app, namespace),
        lambda: backend.core.delete_namespaced_service(args.app, namespace),
        lambda: backend.apps.delete_namespaced_deployment(args.app, namespace),
    )
    for operation in operations:
        try:
            operation()
        except ApiException as exc:
            if exc.status != 404:
                raise
    print(
        f"Application {args.app} supprimée "
        f"(projet {namespace} conservé ; --purge pour tout supprimer)"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GANDAL PaaS (simulation)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    deploy = sub.add_parser("deploy", help="créer ou mettre à jour une application")
    deploy.add_argument("user", help="propriétaire (label uniquement)")
    deploy.add_argument("project", help="nom du projet (namespace proj-{projet})")
    deploy.add_argument("app", help="nom de l'application déployée")
    deploy.add_argument("image", help="référence de l'image")
    deploy.add_argument("port", type=int)
    deploy.add_argument("--replicas", type=int, default=settings.replicas)
    deploy.add_argument("--tag", default=None)
    deploy.add_argument("--digest", default=None)
    deploy.add_argument("--deployment-id", type=int, default=0)
    deploy.set_defaults(fn=cmd_deploy)

    listing = sub.add_parser("list", help="lister les pods avec propriétaire et IP")
    listing.add_argument("--user")
    listing.set_defaults(fn=cmd_list)

    status = sub.add_parser("status", help="état d'une application")
    status.add_argument("user")
    status.add_argument("project")
    status.add_argument("app")
    status.set_defaults(fn=cmd_status)

    delete = sub.add_parser("delete", help="supprimer une application ou un projet")
    delete.add_argument("user")
    delete.add_argument("project")
    delete.add_argument("app", nargs="?")
    delete.add_argument("--purge", action="store_true")
    delete.set_defaults(fn=cmd_delete)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
