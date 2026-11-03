"""Validation et normalisation des noms (DNS-1123) et des labels.

La règle de nommage est celle de Kubernetes : minuscules, chiffres et tirets,
commençant et finissant par un caractère alphanumérique, 63 caractères au plus.
Le backend applique en amont une règle plus stricte (3–30 caractères) ; une
requête qui ne respecte pas DNS-1123 est refusée ici avec un message explicite.
"""

from __future__ import annotations

import re

# RFC 1123 label : utilisé pour les noms de namespace, service, deployment.
DNS1123_LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
MAX_NAME_LENGTH = 63

# Label Kubernetes : autorise aussi '.' et '_' à l'intérieur.
_LABEL_INVALID = re.compile(r"[^a-z0-9._-]+")
_LABEL_EDGE = re.compile(r"^[^a-z0-9]+|[^a-z0-9]+$")

#: Namespaces que l'orchestrateur ne doit jamais créer ni modifier.
RESERVED_NAMESPACES = frozenset(
    {
        "default",
        "kube-system",
        "kube-public",
        "kube-node-lease",
        "gandal-system",
    }
)

NAMESPACE_PREFIX = "proj-"


class InvalidDeployment(ValueError):
    """Requête de déploiement refusée (nom, namespace ou paramètre invalide)."""


def validate_name(value: str, label: str = "nom") -> str:
    """Vérifie qu'une valeur est un label DNS-1123 valide et la renvoie."""
    if not isinstance(value, str) or not value:
        raise InvalidDeployment(f"{label} manquant")
    if len(value) > MAX_NAME_LENGTH:
        raise InvalidDeployment(
            f"{label} '{value}' trop long ({len(value)} > {MAX_NAME_LENGTH})"
        )
    if not DNS1123_LABEL.match(value):
        raise InvalidDeployment(
            f"{label} '{value}' invalide : minuscules, chiffres et tirets "
            "uniquement, sans tiret initial ni final"
        )
    return value


def expected_namespace(project: str) -> str:
    """Namespace attendu pour un projet (convention D3, portée par le backend)."""
    return f"{NAMESPACE_PREFIX}{project}"


def validate_namespace(namespace: str, project: str | None = None) -> str:
    """Vérifie le namespace reçu : convention, non-réservé, DNS-1123.

    Un jeton interne valide n'autorise pas n'importe quel namespace : c'est un
    garde-fou (R12). Si ``project`` est fourni, la correspondance
    ``namespace == proj-{project}`` est exigée.
    """
    validate_name(namespace, "namespace")
    if namespace in RESERVED_NAMESPACES:
        raise InvalidDeployment(f"namespace réservé : '{namespace}'")
    if not namespace.startswith(NAMESPACE_PREFIX):
        raise InvalidDeployment(
            f"namespace '{namespace}' hors convention : préfixe "
            f"'{NAMESPACE_PREFIX}' attendu"
        )
    if project is not None:
        validate_name(project, "projet")
        attendu = expected_namespace(project)
        if namespace != attendu:
            raise InvalidDeployment(
                f"namespace '{namespace}' incohérent avec le projet "
                f"'{project}' (attendu : '{attendu}')"
            )
    return namespace


def normalize_label_value(value: str, default: str = "unknown") -> str:
    """Normalise une valeur de label (nom GitLab, propriétaire…).

    Un nom d'utilisateur GitLab peut contenir ``.``, ``_`` ou des majuscules.
    Les valeurs de label Kubernetes doivent rester en minuscules, sans caractère
    interdit, et faire 63 caractères au plus.
    """
    if not value:
        return default
    normalized = _LABEL_INVALID.sub("-", value.strip().lower())
    normalized = _LABEL_EDGE.sub("", normalized)
    normalized = normalized[:MAX_NAME_LENGTH].strip("-._")
    return normalized or default
