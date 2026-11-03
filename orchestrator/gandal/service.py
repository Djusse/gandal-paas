"""Règles métier de l'orchestrateur.

Le service ne conserve **aucun état** : l'état d'un déploiement vit dans
Kubernetes (annotation et statut du ``Deployment``), ce qui rend un redémarrage
inoffensif (R11). Une boucle de réconciliation relit cet état et rappelle le
backend quand il a changé.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from .config import Settings, settings as default_settings
from .k8s import (
    STATUS_DEPLOYED,
    DeploySpec,
    KubernetesBackend,
    InvalidDeployment,
)
from .notifier import BackendNotifier

log = logging.getLogger("gandal.service")


@dataclass
class DeploymentResult:
    deployment_ref: str
    status: str
    url: str | None = None
    message: str = ""


class DeploymentService:
    """Orchestration : validation, application, lecture d'état et rappels."""

    def __init__(
        self,
        backend: KubernetesBackend,
        notifier: BackendNotifier | None = None,
        cfg: Settings = default_settings,
    ) -> None:
        self.backend = backend
        self.cfg = cfg
        self.notifier = notifier or BackendNotifier(cfg)
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    # ------------------------------------------------------------------ API
    def deploy(self, payload: dict[str, Any]) -> DeploymentResult:
        """Valide puis applique un déploiement. Idempotent par ``deployment_id``.

        Les ressources sont appliquées **avant** de répondre : un ``202`` signifie
        donc que Kubernetes a accepté la définition, pas que l'application est
        déjà disponible (le rollout est suivi par la réconciliation).
        """
        spec = DeploySpec.from_payload(payload, self.cfg)
        url = self.backend.apply(spec)
        return DeploymentResult(
            deployment_ref=f"orch-{spec.deployment_id}",
            status="deploying",
            url=url,
            message="ressources appliquées, rollout en cours",
        )

    def state(self, deployment_id: int) -> DeploymentResult | None:
        """État courant lu dans Kubernetes, ou ``None`` si inconnu."""
        deployment = self.backend.read_deployment(deployment_id)
        if deployment is None:
            return None
        state = self.backend.state_of(deployment)
        return DeploymentResult(
            deployment_ref=f"orch-{deployment_id}",
            status=state.status,
            url=state.url,
            message=state.message,
        )

    def delete_project(self, namespace: str) -> None:
        self.backend.delete_namespace(namespace)

    # --------------------------------------------------- réconciliation
    async def reconcile_once(self) -> int:
        """Parcourt les déploiements gérés et rappelle le backend si nécessaire.

        Retourne le nombre de rappels envoyés avec succès.
        """
        sent = 0
        try:
            deployments = self.backend.list_managed()
        except Exception:  # pragma: no cover - dépend du cluster
            log.exception("lecture des déploiements gérés impossible")
            return 0

        for deployment in deployments:
            try:
                sent += await self._reconcile_deployment(deployment)
            except Exception:  # pragma: no cover - un déploiement cassé ne bloque pas les autres
                log.exception(
                    "réconciliation impossible pour %s",
                    getattr(getattr(deployment, "metadata", None), "name", "?"),
                )
        return sent

    async def _reconcile_deployment(self, deployment: Any) -> int:
        state = self.backend.state_of(deployment)
        if not state.final or not state.needs_report:
            return 0

        delivered = await self.notifier.send_status(
            deployment_id=state.deployment_id,
            status=state.status,
            url=state.url,
            message=state.message,
        )
        if not delivered:
            return 0

        try:
            self.backend.mark_reported(deployment, state.status)
        except Exception:  # pragma: no cover - annotation déjà posée ou conflit
            log.warning(
                "annotation de statut non écrite pour %s", state.deployment_id
            )
        return 1

    async def run_reconciler(self) -> None:
        """Boucle infinie ; s'arrête proprement quand ``stop()`` est appelé."""
        interval = max(1, self.cfg.reconcile_interval)
        log.info("boucle de réconciliation démarrée (intervalle %s s)", interval)
        while not self._stopping.is_set():
            await self.reconcile_once()
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue
        log.info("boucle de réconciliation arrêtée")

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping.clear()
            self._task = asyncio.create_task(self.run_reconciler())

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):  # pragma: no cover
                self._task.cancel()
            self._task = None


#: Statuts exposés par ``GET /deployments/{id}``.
VALID_STATUSES = ("deploying", STATUS_DEPLOYED, "failed")

__all__ = [
    "DeploymentResult",
    "DeploymentService",
    "InvalidDeployment",
    "VALID_STATUSES",
]
