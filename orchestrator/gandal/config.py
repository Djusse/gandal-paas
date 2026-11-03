"""Configuration de l'orchestrateur, lue dans l'environnement.

Aucune convention de nommage n'est calculée ici : le backend reste le seul
propriétaire du namespace et de l'URL (décision D3). Ce module ne contient que
des valeurs d'infrastructure.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:  # pragma: no cover - configuration invalide
        raise ValueError(f"{name} doit être un entier (reçu : {raw!r})") from exc


@dataclass(frozen=True)
class Settings:
    """Valeurs de configuration, immuables après lecture."""

    # --- Identité de la plateforme ---------------------------------------
    base_domain: str = os.getenv("GANDAL_BASE_DOMAIN", "gandal.test")
    ingress_class: str = os.getenv("GANDAL_INGRESS_CLASS", "traefik")

    # --- Valeurs par défaut des déploiements -----------------------------
    replicas: int = _int_env("GANDAL_REPLICAS", 2)

    # --- Quotas par projet ------------------------------------------------
    quota_requests_cpu: str = os.getenv("GANDAL_QUOTA_REQ_CPU", "1")
    quota_requests_memory: str = os.getenv("GANDAL_QUOTA_REQ_MEM", "1Gi")
    quota_limits_cpu: str = os.getenv("GANDAL_QUOTA_LIM_CPU", "2")
    quota_limits_memory: str = os.getenv("GANDAL_QUOTA_LIM_MEM", "2Gi")
    quota_pods: str = os.getenv("GANDAL_QUOTA_PODS", "4")

    # --- Ressources par conteneur ----------------------------------------
    container_requests_cpu: str = os.getenv("GANDAL_CTR_REQ_CPU", "100m")
    container_requests_memory: str = os.getenv("GANDAL_CTR_REQ_MEM", "128Mi")
    container_limits_cpu: str = os.getenv("GANDAL_CTR_LIM_CPU", "500m")
    container_limits_memory: str = os.getenv("GANDAL_CTR_LIM_MEM", "512Mi")

    # --- Service HTTP -----------------------------------------------------
    orchestrator_token: str = os.getenv("ORCHESTRATOR_TOKEN", "change-me-long-random")
    backend_url: str = os.getenv("BACKEND_URL", "http://localhost:8000")
    internal_token: str = os.getenv("INTERNAL_TOKEN", "change-me-long-random")
    host: str = os.getenv("ORCHESTRATOR_HOST", "0.0.0.0")
    port: int = _int_env("ORCHESTRATOR_PORT", 8100)

    # --- Boucle de réconciliation ---------------------------------------
    reconcile_interval: int = _int_env("GANDAL_RECONCILE_INTERVAL", 30)
    rollout_timeout: int = _int_env("GANDAL_ROLLOUT_TIMEOUT", 300)
    callback_attempts: int = _int_env("GANDAL_CALLBACK_ATTEMPTS", 5)
    callback_backoff: float = float(os.getenv("GANDAL_CALLBACK_BACKOFF", "2"))
    request_timeout: float = float(os.getenv("GANDAL_REQUEST_TIMEOUT", "15"))

    # --- Environnement d'exécution --------------------------------------
    kubeconfig: str | None = os.getenv("KUBECONFIG") or None
    in_cluster: bool = os.getenv("GANDAL_IN_CLUSTER", "").lower() in ("1", "true", "yes")

    @property
    def quota(self) -> dict[str, str]:
        return {
            "requests.cpu": self.quota_requests_cpu,
            "requests.memory": self.quota_requests_memory,
            "limits.cpu": self.quota_limits_cpu,
            "limits.memory": self.quota_limits_memory,
            "pods": self.quota_pods,
        }


settings = Settings()
