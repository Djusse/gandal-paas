"""Routes HTTP de l'orchestrateur.

- ``POST /deployments``          : applique un déploiement (idempotent) ;
- ``GET  /deployments/{id}``     : état courant lu dans Kubernetes ;
- ``DELETE /projects/{namespace}``: purge d'un namespace applicatif ;
- ``GET  /health``               : sonde de vie.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from gandal.k8s import InvalidDeployment
from gandal.service import DeploymentService

from .dependencies import get_service, require_token
from .schemas import (
    DeploymentAccepted,
    DeploymentRequest,
    DeploymentState,
)

log = logging.getLogger("orchestrator.routes")

router = APIRouter()


@router.post(
    "/deployments",
    response_model=DeploymentAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_token)],
)
def create_deployment(payload: DeploymentRequest, service: DeploymentService = Depends(get_service)):
    """Valide puis applique les ressources ; répond une fois Kubernetes informé."""
    try:
        result = service.deploy(payload.model_dump())
    except InvalidDeployment as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return DeploymentAccepted(
        deployment_ref=result.deployment_ref,
        status=result.status,
        url=result.url,
        message=result.message,
    )


@router.get(
    "/deployments/{deployment_id}",
    response_model=DeploymentState,
    dependencies=[Depends(require_token)],
)
def read_deployment(deployment_id: int, service: DeploymentService = Depends(get_service)):
    """État du déploiement, utilisé par le backend comme repli."""
    result = service.state(deployment_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"déploiement {deployment_id} inconnu",
        )
    return DeploymentState(
        deployment_ref=result.deployment_ref,
        status=result.status,
        url=result.url,
        message=result.message,
    )


@router.delete(
    "/projects/{namespace}",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_token)],
)
def delete_project(namespace: str, service: DeploymentService = Depends(get_service)):
    """Supprime un namespace applicatif (garde-fou : label ``gandal.io/managed``)."""
    try:
        service.delete_project(namespace)
    except InvalidDeployment as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"deleted": namespace}
