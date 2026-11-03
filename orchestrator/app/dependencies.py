"""Dépendances FastAPI : authentification et accès au service de déploiement."""

from __future__ import annotations

import hmac
import logging

from fastapi import Header, HTTPException, Request, status

from gandal.config import settings

log = logging.getLogger("orchestrator.auth")

TOKEN_HEADER = "X-Orchestrator-Token"


def _expected_token(request: Request) -> str:
    """Jeton attendu : celui du service configuré, sinon la configuration globale."""
    service = getattr(request.app.state, "deployment_service", None)
    cfg = getattr(service, "cfg", None) or getattr(request.app.state, "settings", None)
    return getattr(cfg, "orchestrator_token", settings.orchestrator_token)


async def require_token(
    request: Request,
    x_orchestrator_token: str | None = Header(default=None, alias=TOKEN_HEADER),
) -> None:
    """Vérifie le jeton partagé avec le backend.

    L'orchestrateur n'est joignable que par le backend : sans ce jeton, une
    requête ne peut pas déclencher de déploiement.
    """
    expected = _expected_token(request)
    if not x_orchestrator_token or not hmac.compare_digest(
        x_orchestrator_token, expected
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"jeton absent ou invalide (en-tête {TOKEN_HEADER})",
        )


def get_service(request: Request):
    """Retourne le service de déploiement attaché à l'application."""
    service = getattr(request.app.state, "deployment_service", None)
    if service is None:  # pragma: no cover - configuration incomplète
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="service de déploiement non initialisé",
        )
    return service
