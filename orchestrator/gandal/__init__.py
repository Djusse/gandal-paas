"""Bibliothèque de l'orchestrateur GANDAL PaaS.

- :mod:`gandal.config`  — configuration (variables d'environnement)
- :mod:`gandal.names`   — validation et normalisation des noms
- :mod:`gandal.k8s`     — application des ressources Kubernetes
- :mod:`gandal.service` — règles métier : idempotence, statut, rappels
"""

from .config import settings
from .k8s import DeploySpec, InvalidDeployment, KubernetesBackend
from .names import normalize_label_value, validate_namespace, validate_name

__all__ = [
    "settings",
    "DeploySpec",
    "InvalidDeployment",
    "KubernetesBackend",
    "normalize_label_value",
    "validate_namespace",
    "validate_name",
]
