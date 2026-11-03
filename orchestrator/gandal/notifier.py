"""Client de rappel vers le backend (``POST /internal/deployments/{id}/status``)."""

from __future__ import annotations

import logging

import httpx

from .config import Settings, settings as default_settings

log = logging.getLogger("gandal.notifier")


class BackendNotifier:
    """Envoie les changements d'état du déploiement au backend.

    Les erreurs réseau ne sont pas propagées : elles sont journalisées et
    signalées par un booléen, pour que la boucle de réconciliation puisse
    réessayer au tour suivant (les rappels sont idempotents côté backend).
    """

    def __init__(self, cfg: Settings = default_settings, transport: httpx.AsyncBaseTransport | None = None):
        self.cfg = cfg
        self._transport = transport

    @property
    def status_url(self) -> str:
        return f"{self.cfg.backend_url.rstrip('/')}/internal/deployments"

    async def send_status(
        self,
        deployment_id: int,
        status: str,
        url: str | None = None,
        message: str = "",
    ) -> bool:
        payload = {"status": status, "url": url, "message": message or ""}
        endpoint = f"{self.status_url}/{deployment_id}/status"
        headers = {"X-Internal-Token": self.cfg.internal_token}

        for attempt in range(1, self.cfg.callback_attempts + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self.cfg.request_timeout, transport=self._transport
                ) as client:
                    response = await client.post(endpoint, json=payload, headers=headers)
                if response.status_code < 400:
                    log.info(
                        "rappel %s -> %s (%s)", deployment_id, status, response.status_code
                    )
                    return True
                log.warning(
                    "rappel %s refusé (%s), tentative %s/%s",
                    deployment_id,
                    response.status_code,
                    attempt,
                    self.cfg.callback_attempts,
                )
            except httpx.HTTPError as exc:
                log.warning(
                    "rappel %s en échec (%s), tentative %s/%s",
                    deployment_id,
                    exc,
                    attempt,
                    self.cfg.callback_attempts,
                )

            if attempt < self.cfg.callback_attempts:
                import asyncio

                await asyncio.sleep(self.cfg.callback_backoff * attempt)

        return False
