"""Application des ressources Kubernetes pour un déploiement GANDAL.

Le module est volontairement dépourvu de calcul de convention : il reçoit
``namespace``, ``host``, ``labels`` et la référence d'image depuis l'appelant
(le backend est propriétaire de ces valeurs, décision D3).

Toutes les opérations sont **idempotentes** : une ressource déjà présente est
mise à jour (``patch``) au lieu d'échouer sur un ``409``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import Settings, settings as default_settings
from .names import (
    InvalidDeployment,
    expected_namespace,
    normalize_label_value,
    validate_name,
    validate_namespace,
)

log = logging.getLogger("gandal.k8s")

MANAGED_LABEL = "gandal.io/managed"
OWNER_LABEL = "gandal.io/owner"
PROJECT_LABEL = "gandal.io/project"
APP_LABEL = "gandal.io/app"

DEPLOYMENT_ID_LABEL = "gandal.io/deployment-id"
DEPLOYMENT_ID_ANNOTATION = "gandal.io/deployment-id"
REPORTED_STATUS_ANNOTATION = "gandal.io/reported-status"
IMAGE_ANNOTATION = "gandal.io/image"
URL_ANNOTATION = "gandal.io/url"

LIMIT_RANGE_NAME = "default-limits"
QUOTA_NAME = "project-quota"
NETWORK_POLICY_NAME = "isolate-ingress"

#: États exposés au backend.
STATUS_DEPLOYING = "deploying"
STATUS_DEPLOYED = "deployed"
STATUS_FAILED = "failed"


@dataclass(frozen=True)
class DeploySpec:
    """Demande de déploiement validée, prête à être appliquée."""

    deployment_id: int
    project: str
    owner: str
    namespace: str
    image: str
    port: int
    tag: str | None = None
    digest: str | None = None
    replicas: int = 2
    base_domain: str = field(default="", compare=False)

    @property
    def app(self) -> str:
        """Nom des ressources applicatives : le nom du projet (1 projet = 1 app)."""
        return self.project

    @property
    def image_ref(self) -> str:
        """``repository@digest`` si connu, sinon ``repository:tag``.

        Le digest est préféré au tag : un tag est mutable, un digest ne l'est pas.
        """
        if self.digest:
            return f"{self.image}@{self.digest}"
        if self.tag:
            return f"{self.image}:{self.tag}"
        return self.image

    def host(self, base_domain: str) -> str:
        return f"{self.project}.{base_domain.lstrip('.')}"

    @property
    def labels(self) -> dict[str, str]:
        return {
            OWNER_LABEL: normalize_label_value(self.owner),
            PROJECT_LABEL: self.project,
            APP_LABEL: self.app,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any], cfg: Settings = default_settings) -> "DeploySpec":
        """Valide un corps de requête ``POST /deployments``.

        Lève :class:`InvalidDeployment` si un champ est absent ou invalide.
        """
        required = ("deployment_id", "project", "namespace", "image", "port")
        missing = [name for name in required if payload.get(name) in (None, "")]
        if missing:
            raise InvalidDeployment(f"champs obligatoires manquants : {', '.join(missing)}")

        try:
            deployment_id = int(payload["deployment_id"])
        except (TypeError, ValueError) as exc:
            raise InvalidDeployment("deployment_id doit être un entier") from exc
        if deployment_id <= 0:
            raise InvalidDeployment("deployment_id doit être strictement positif")

        project = validate_name(str(payload["project"]), "projet")
        namespace = validate_namespace(str(payload["namespace"]), project)

        port = payload["port"]
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise InvalidDeployment(f"port invalide : {port!r}")

        replicas = payload.get("replicas", cfg.replicas)
        if not isinstance(replicas, int) or not 1 <= replicas <= 10:
            raise InvalidDeployment(f"replicas invalide : {replicas!r} (1 à 10)")

        image = str(payload["image"]).strip()
        if not image:
            raise InvalidDeployment("image vide")

        return cls(
            deployment_id=deployment_id,
            project=project,
            owner=str(payload.get("owner") or ""),
            namespace=namespace,
            image=image,
            port=port,
            tag=payload.get("tag") or None,
            digest=payload.get("digest") or None,
            replicas=replicas,
            base_domain=cfg.base_domain,
        )


@dataclass
class DeploymentState:
    """État d'un déploiement lu dans Kubernetes."""

    deployment_id: int
    status: str
    url: str | None
    message: str
    reported_status: str | None = None

    @property
    def final(self) -> bool:
        return self.status in (STATUS_DEPLOYED, STATUS_FAILED)

    @property
    def needs_report(self) -> bool:
        return self.final and self.reported_status != self.status


class KubernetesBackend:
    """Client Kubernetes de haut niveau, limité aux ressources du PaaS.

    Les API sont injectables pour permettre les tests sans cluster.
    """

    def __init__(
        self,
        core: Any,
        apps: Any,
        networking: Any,
        cfg: Settings = default_settings,
    ) -> None:
        self.core = core
        self.apps = apps
        self.networking = networking
        self.cfg = cfg

    # ------------------------------------------------------------------ init
    @classmethod
    def from_environment(cls, cfg: Settings = default_settings) -> "KubernetesBackend":
        """Charge la configuration in-cluster (ou kubeconfig) et construit le client."""
        from kubernetes import client, config

        if cfg.in_cluster:
            config.load_incluster_config()
        else:
            config.load_kube_config(config_file=cfg.kubeconfig)

        return cls(
            core=client.CoreV1Api(),
            apps=client.AppsV1Api(),
            networking=client.NetworkingV1Api(),
            cfg=cfg,
        )

    # ------------------------------------------------------------------ utils
    @staticmethod
    def _create_or_patch(create, patch, name: str) -> str:
        """Crée la ressource, ou la met à jour si elle existe déjà (409)."""
        from kubernetes.client.rest import ApiException

        try:
            create()
            return "created"
        except ApiException as exc:
            if exc.status != 409:
                raise
            patch()
            return "updated"

    def _namespace_labels(self, spec: DeploySpec) -> dict[str, str]:
        return {
            MANAGED_LABEL: "true",
            OWNER_LABEL: normalize_label_value(spec.owner),
            PROJECT_LABEL: spec.project,
        }

    def namespace_is_managed(self, namespace: str) -> bool:
        """Vérifie le label ``gandal.io/managed`` avant toute modification (R12)."""
        from kubernetes.client.rest import ApiException

        try:
            ns = self.core.read_namespace(namespace)
        except ApiException as exc:
            if exc.status == 404:
                return False
            raise
        labels = (ns.metadata.labels or {}) if ns and ns.metadata else {}
        return labels.get(MANAGED_LABEL) == "true"

    # ------------------------------------------------------------- ressources
    def ensure_namespace(self, spec: DeploySpec) -> None:
        body = {
            "metadata": {
                "name": spec.namespace,
                "labels": self._namespace_labels(spec),
            }
        }
        self._create_or_patch(
            lambda: self.core.create_namespace(body),
            lambda: self.core.patch_namespace(spec.namespace, body),
            spec.namespace,
        )

    def ensure_limit_range(self, spec: DeploySpec) -> None:
        body = {
            "metadata": {"name": LIMIT_RANGE_NAME, "labels": spec.labels},
            "spec": {
                "limits": [
                    {
                        "type": "Container",
                        "default": {
                            "cpu": self.cfg.container_limits_cpu,
                            "memory": self.cfg.container_limits_memory,
                        },
                        "defaultRequest": {
                            "cpu": self.cfg.container_requests_cpu,
                            "memory": self.cfg.container_requests_memory,
                        },
                    }
                ]
            },
        }
        ns = spec.namespace
        self._create_or_patch(
            lambda: self.core.create_namespaced_limit_range(ns, body),
            lambda: self.core.patch_namespaced_limit_range(LIMIT_RANGE_NAME, ns, body),
            LIMIT_RANGE_NAME,
        )

    def ensure_resource_quota(self, spec: DeploySpec) -> None:
        body = {
            "metadata": {"name": QUOTA_NAME, "labels": spec.labels},
            "spec": {"hard": self.cfg.quota},
        }
        ns = spec.namespace
        self._create_or_patch(
            lambda: self.core.create_namespaced_resource_quota(ns, body),
            lambda: self.core.patch_namespaced_resource_quota(QUOTA_NAME, ns, body),
            QUOTA_NAME,
        )

    def ensure_network_policy(self, spec: DeploySpec) -> None:
        body = {
            "metadata": {"name": NETWORK_POLICY_NAME, "labels": spec.labels},
            "spec": {
                "podSelector": {},
                "policyTypes": ["Ingress"],
                "ingress": [
                    {"from": [{"podSelector": {}}]},
                    {
                        "from": [
                            {
                                "namespaceSelector": {
                                    "matchLabels": {
                                        "kubernetes.io/metadata.name": "kube-system"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "from": [
                            {
                                "namespaceSelector": {
                                    "matchLabels": {
                                        "kubernetes.io/metadata.name": "gandal-system"
                                    }
                                }
                            }
                        ]
                    },
                ],
            },
        }
        ns = spec.namespace
        self._create_or_patch(
            lambda: self.networking.create_namespaced_network_policy(ns, body),
            lambda: self.networking.patch_namespaced_network_policy(
                NETWORK_POLICY_NAME, ns, body
            ),
            NETWORK_POLICY_NAME,
        )

    def ensure_deployment(self, spec: DeploySpec) -> None:
        labels = dict(spec.labels)
        labels[MANAGED_LABEL] = "true"
        labels[DEPLOYMENT_ID_LABEL] = str(spec.deployment_id)

        probe = {"tcpSocket": {"port": spec.port}, "periodSeconds": 5}
        body = {
            "metadata": {
                "name": spec.app,
                "labels": labels,
                "annotations": {
                    DEPLOYMENT_ID_ANNOTATION: str(spec.deployment_id),
                    IMAGE_ANNOTATION: spec.image_ref,
                    URL_ANNOTATION: f"http://{spec.host(self.cfg.base_domain)}",
                },
            },
            "spec": {
                "replicas": spec.replicas,
                "selector": {"matchLabels": {APP_LABEL: spec.app}},
                "template": {
                    "metadata": {"labels": labels},
                    "spec": {
                        "containers": [
                            {
                                "name": spec.app,
                                "image": spec.image_ref,
                                "ports": [{"containerPort": spec.port}],
                                "readinessProbe": dict(probe, initialDelaySeconds=3),
                                "livenessProbe": dict(probe, initialDelaySeconds=10),
                                "resources": {
                                    "requests": {
                                        "cpu": self.cfg.container_requests_cpu,
                                        "memory": self.cfg.container_requests_memory,
                                    },
                                    "limits": {
                                        "cpu": self.cfg.container_limits_cpu,
                                        "memory": self.cfg.container_limits_memory,
                                    },
                                },
                            }
                        ]
                    },
                },
            },
        }
        ns = spec.namespace
        self._create_or_patch(
            lambda: self.apps.create_namespaced_deployment(ns, body),
            lambda: self.apps.patch_namespaced_deployment(spec.app, ns, body),
            spec.app,
        )

    def ensure_service(self, spec: DeploySpec) -> None:
        body = {
            "metadata": {"name": spec.app, "labels": spec.labels},
            "spec": {
                "selector": {APP_LABEL: spec.app},
                "ports": [{"port": 80, "targetPort": spec.port}],
            },
        }
        ns = spec.namespace
        self._create_or_patch(
            lambda: self.core.create_namespaced_service(ns, body),
            lambda: self.core.patch_namespaced_service(spec.app, ns, body),
            spec.app,
        )

    def ensure_ingress(self, spec: DeploySpec) -> str:
        host = spec.host(self.cfg.base_domain)
        body = {
            "metadata": {"name": spec.app, "labels": spec.labels},
            "spec": {
                "ingressClassName": self.cfg.ingress_class,
                "rules": [
                    {
                        "host": host,
                        "http": {
                            "paths": [
                                {
                                    "path": "/",
                                    "pathType": "Prefix",
                                    "backend": {
                                        "service": {
                                            "name": spec.app,
                                            "port": {"number": 80},
                                        }
                                    },
                                }
                            ]
                        },
                    }
                ],
            },
        }
        ns = spec.namespace
        self._create_or_patch(
            lambda: self.networking.create_namespaced_ingress(ns, body),
            lambda: self.networking.patch_namespaced_ingress(spec.app, ns, body),
            spec.app,
        )
        return host

    def apply(self, spec: DeploySpec) -> str:
        """Applique toutes les ressources, dans l'ordre attendu par Kubernetes.

        Retourne l'URL publique de l'application.
        """
        self.ensure_namespace(spec)
        self.ensure_limit_range(spec)
        self.ensure_resource_quota(spec)
        self.ensure_network_policy(spec)
        self.ensure_deployment(spec)
        self.ensure_service(spec)
        host = self.ensure_ingress(spec)
        log.info(
            "deployment %s appliqué dans %s (image %s, %s réplicas)",
            spec.deployment_id,
            spec.namespace,
            spec.image_ref,
            spec.replicas,
        )
        return f"http://{host}"

    # ------------------------------------------------------------------ état
    def read_deployment(self, deployment_id: int) -> Any | None:
        """Retourne le ``Deployment`` portant l'identifiant donné, ou ``None``."""
        selector = f"{DEPLOYMENT_ID_ANNOTATION}={deployment_id}"
        result = self.apps.list_deployment_for_all_namespaces(label_selector=selector)
        items = list(getattr(result, "items", []) or [])
        if not items:
            return None
        # En cas de doublon (ne devrait pas arriver), le plus récent l'emporte.
        return items[0]

    def state_of(self, deployment: Any, cfg: Settings | None = None) -> DeploymentState:
        """Traduit un objet ``Deployment`` en état métier."""
        cfg = cfg or self.cfg
        metadata = deployment.metadata
        labels = metadata.labels or {}
        annotations = metadata.annotations or {}
        status = deployment.status
        spec = deployment.spec

        deployment_id = int(
            annotations.get(DEPLOYMENT_ID_ANNOTATION) or labels.get(DEPLOYMENT_ID_ANNOTATION) or 0
        )
        url = annotations.get(URL_ANNOTATION)
        reported = annotations.get(REPORTED_STATUS_ANNOTATION)

        ready = status.ready_replicas or 0
        desired = spec.replicas if spec and spec.replicas is not None else cfg.replicas

        if ready >= desired and desired > 0:
            return DeploymentState(deployment_id, STATUS_DEPLOYED, url, "", reported)

        # Échec explicite : ProgressDeadlineExceeded.
        for condition in status.conditions or []:
            if (
                condition.type == "Progressing"
                and condition.status == "False"
                and condition.reason == "ProgressDeadlineExceeded"
            ):
                message = condition.message or "délai de déploiement dépassé"
                return DeploymentState(deployment_id, STATUS_FAILED, url, message, reported)

        # Échec par expiration de notre propre délai.
        created = metadata.creation_timestamp
        if created is not None and cfg.rollout_timeout > 0:
            reference = datetime.now(timezone.utc)
            if created.tzinfo is None:  # pragma: no cover - dépend du client
                created = created.replace(tzinfo=timezone.utc)
            if reference - created > timedelta(seconds=cfg.rollout_timeout):
                message = f"délai de {cfg.rollout_timeout} s dépassé ({ready}/{desired} prêts)"
                return DeploymentState(deployment_id, STATUS_FAILED, url, message, reported)

        message = f"{ready}/{desired} réplicas prêts"
        return DeploymentState(deployment_id, STATUS_DEPLOYING, url, message, reported)

    def mark_reported(self, deployment: Any, status: str) -> None:
        """Inscrit le statut déjà transmis au backend (évite les rappels en boucle)."""
        metadata = deployment.metadata
        body = {
            "metadata": {
                "annotations": {
                    REPORTED_STATUS_ANNOTATION: status,
                }
            }
        }
        self.apps.patch_namespaced_deployment(
            metadata.name, metadata.namespace, body
        )

    def list_managed(self) -> list[Any]:
        selector = f"{MANAGED_LABEL}=true"
        result = self.apps.list_deployment_for_all_namespaces(label_selector=selector)
        return list(getattr(result, "items", []) or [])

    # ------------------------------------------------------------- nettoyage
    def delete_namespace(self, namespace: str) -> None:
        """Supprime un namespace applicatif (garde-fou : label ``managed``)."""
        from kubernetes.client.rest import ApiException

        validate_namespace(namespace)
        if not self.namespace_is_managed(namespace):
            raise InvalidDeployment(
                f"namespace '{namespace}' non géré par GANDAL : suppression refusée"
            )
        try:
            self.core.delete_namespace(namespace)
        except ApiException as exc:
            if exc.status != 404:
                raise


def namespace_for(project: str) -> str:
    """Raccourci public pour la convention ``proj-{nom}``."""
    return expected_namespace(project)
