"""Règles communes de création et de suivi d'un déploiement.

Ce module centralise deux corrections du plan :

- **R1** : la ligne ``Deployment`` est commitée *avant* l'appel à
  l'orchestrateur, dans un état ``requested`` visible des autres connexions.
  Le callback ne peut donc plus tomber sur un 404 ni être écrasé par un commit
  tardif.
- **R11 / D9** : l'état vit dans Kubernetes. Une relance périodique renvoie les
  déploiements restés ``requested`` et interroge ceux restés ``deploying``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Deployment, Image, Project

log = logging.getLogger("deployment-service")

#: Un déploiement dans cet état est définitif : il ne doit plus changer.
FINAL_STATUSES = ("deployed", "failed")

#: Ordre de progression : un callback ne peut jamais faire reculer l'état.
_STATUS_RANK = {"requested": 0, "deploying": 1, "deployed": 2, "failed": 2}


def is_monotonic(current: str, incoming: str) -> bool:
    """``True`` si le statut entrant peut remplacer le statut courant.

    ``deployed`` et ``failed`` sont terminaux : un ``deploying`` tardif ne les
    écrase pas (R1).
    """
    if current in FINAL_STATUSES:
        return False
    return _STATUS_RANK.get(incoming, 0) >= _STATUS_RANK.get(current, 0)


def build_deploy_request(project: Project, deployment: Deployment, image: Image) -> dict:
    """Construit le corps envoyé à l'orchestrateur (contrat §5 du plan)."""
    return {
        "deployment_id": deployment.id,
        "project": project.name,
        "owner": project.owner,
        "namespace": project.k8s_namespace,
        "image": image.repository,
        "tag": image.tag,
        "digest": image.digest,
        "port": project.app_port,
        "replicas": settings.default_replicas,
    }


async def send_deployment(
    db: Session,
    orch,
    project: Project,
    deployment: Deployment,
    image: Image,
) -> None:
    """Appelle l'orchestrateur pour un déploiement déjà commité (``requested``).

    L'appel est idempotent côté orchestrateur : le rejouer met à jour les
    ressources sans créer de doublon.
    """
    request = build_deploy_request(project, deployment, image)
    try:
        result = await orch.deploy(request)
    except Exception as exc:
        log.warning("appel orchestrateur échoué pour le déploiement %s : %s", deployment.id, exc)
        deployment.status = "failed"
        deployment.message = str(exc)[:500]
        project.status = "failed"
        project.error = str(exc)[:500]
        db.commit()
        raise

    deployment.orchestrator_ref = result.get("deployment_ref")
    if deployment.status == "requested":
        deployment.status = "deploying"
    if project.status not in FINAL_STATUSES:
        project.status = "deploying"
    db.commit()


# --------------------------------------------------------------- relance
class DeploymentRecovery:
    """Tâche périodique de rattrapage (R1, R11).

    - un déploiement ``requested`` depuis plus de ``requested_timeout`` s est
      renvoyé à l'orchestrateur (couvre « commit réussi, requête perdue ») ;
    - un déploiement ``deploying`` depuis plus de ``deploying_timeout`` s est
      interrogé via ``GET /deployments/{id}`` et son statut est rattrapé.
    """

    def __init__(self, orchestrator_factory: Callable[[], object]):
        self._orchestrator_factory = orchestrator_factory
        self._task: asyncio.Task | None = None
        # L'événement est créé dans la boucle courante (``start``) : un objet
        # asyncio partagé entre deux boucles (tests, rechargement) est invalide.
        self._stopping: asyncio.Event | None = None

    # -------------------------------------------------------------- boucle
    async def run(self) -> None:
        interval = max(5, settings.recovery_interval)
        log.info("relance périodique démarrée (intervalle %ss)", interval)
        stopping = self._stopping or asyncio.Event()
        self._stopping = stopping
        while not stopping.is_set():
            try:
                await self.recover_once()
            except Exception:  # pragma: no cover - ne doit pas tuer la boucle
                log.exception("erreur pendant la relance périodique")
            try:
                await asyncio.wait_for(stopping.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue
        log.info("relance périodique arrêtée")

    def start(self) -> None:
        if not settings.recovery_enabled:
            log.info("relance périodique désactivée (RECOVERY_ENABLED=false)")
            return
        if self._task is None or self._task.done():
            self._stopping = asyncio.Event()
            self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        if self._stopping is not None:
            self._stopping.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):  # pragma: no cover
                self._task.cancel()
            self._task = None

    # -------------------------------------------------------------- travail
    async def recover_once(self, now=None) -> int:
        """Exécute un tour de rattrapage. Retourne le nombre d'actions réussies."""
        from datetime import datetime

        now = now or datetime.now()
        actions = 0
        orch = self._orchestrator_factory()

        db = SessionLocal()
        try:
            pending = db.query(Deployment).filter(
                Deployment.status.in_(("requested", "deploying"))
            ).all()

            for deployment in pending:
                created = deployment.created_at or now
                age = (now - created).total_seconds()

                if deployment.status == "requested":
                    if age < settings.requested_timeout:
                        continue
                    project = db.get(Project, deployment.project_id)
                    image = db.get(Image, deployment.image_id)
                    if not project or not image:
                        continue
                    log.info("relance du déploiement %s (requested)", deployment.id)
                    try:
                        await send_deployment(db, orch, project, deployment, image)
                        actions += 1
                    except Exception as exc:
                        log.warning("relance %s échouée : %s", deployment.id, exc)
                    continue

                # status == "deploying"
                if age < settings.deploying_timeout:
                    continue
                if not hasattr(orch, "get_deployment"):
                    continue
                log.info("interrogation du déploiement %s (deploying)", deployment.id)
                try:
                    state = await orch.get_deployment(deployment.id)
                except Exception as exc:
                    log.warning("interrogation %s échouée : %s", deployment.id, exc)
                    continue

                incoming = state.get("status")
                if incoming in ("deployed", "failed") and is_monotonic(deployment.status, incoming):
                    deployment.status = incoming
                    deployment.url = state.get("url") or deployment.url
                    deployment.message = state.get("message") or ""
                    project = db.get(Project, deployment.project_id)
                    if project:
                        project.status = incoming
                        project.error = (
                            state.get("message") or None if incoming == "failed" else None
                        )
                    db.commit()
                    actions += 1
        finally:
            db.close()

        return actions
