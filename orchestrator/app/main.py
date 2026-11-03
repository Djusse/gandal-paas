"""Application FastAPI de l'orchestrateur GANDAL PaaS.

L'état des déploiements vit dans Kubernetes ; l'application ne fait que le
lire, l'appliquer et le rapporter au backend (R11, D9).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from gandal.config import settings
from gandal.k8s import KubernetesBackend
from gandal.service import DeploymentService

from . import __version__
from .routes import router
from .schemas import HealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("orchestrator")


def _build_service() -> DeploymentService:
    backend = KubernetesBackend.from_environment(settings)
    return DeploymentService(backend=backend, cfg=settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Démarre la réconciliation avec l'application, l'arrête proprement."""
    # Un service déjà fourni (tests, injection) est conservé tel quel.
    injected = getattr(app.state, "deployment_service", None) is not None

    if not injected:
        try:
            service = _build_service()
        except Exception:  # pragma: no cover - cluster ou kubeconfig absent
            log.exception(
                "client Kubernetes indisponible : les routes de déploiement échoueront"
            )
            app.state.deployment_service = None
            app.state.kubernetes_ready = False
        else:
            app.state.deployment_service = service
            app.state.kubernetes_ready = True
            service.start()

    try:
        yield
    finally:
        service = getattr(app.state, "deployment_service", None)
        if service is not None and not injected:
            await service.stop()


app = FastAPI(
    title="GANDAL PaaS Orchestrator",
    description=(
        "Plan d'exécution : traduit une demande de déploiement en ressources "
        "Kubernetes (namespace, quotas, isolation, Deployment, Service, Ingress) "
        "et rapporte l'état au backend."
    ),
    version=__version__,
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    service = getattr(app.state, "deployment_service", None)
    return HealthResponse(
        status="ok",
        version=__version__,
        kubernetes=getattr(app.state, "kubernetes_ready", False),
        reconciler=service is not None and service._task is not None,
    )


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "service": "GANDAL PaaS Orchestrator",
        "version": __version__,
        "docs_url": "/docs",
    }
