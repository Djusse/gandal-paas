import asyncio
import logging

import httpx

from app.config import settings

log = logging.getLogger("orchestrator-real")

TOKEN_HEADER = "X-Orchestrator-Token"


class OrchestratorError(RuntimeError):
    """Échec définitif de l'appel à l'orchestrateur."""


class OrchestratorReal:
    """Client HTTP de l'orchestrateur (plan d'exécution).

    - jeton partagé (``ORCHESTRATOR_TOKEN``) sur chaque requête ;
    - délai d'attente et nombre de tentatives configurables ;
    - ``get_deployment`` sert de repli quand un rappel s'est perdu.
    """

    def __init__(self):
        self.base_url = settings.orchestrator_url.rstrip("/")
        if not self.base_url:
            raise OrchestratorError("ORCHESTRATOR_URL n'est pas configurée")
        self.timeout = settings.orchestrator_timeout
        self.retries = max(1, settings.orchestrator_retries)
        self.headers = {TOKEN_HEADER: settings.orchestrator_token}

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = f"{self.base_url}{path}"
        last_error: Exception | None = None

        for attempt in range(1, self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(
                        method, url, headers=self.headers, **kwargs
                    )
                if response.status_code < 500:
                    return response
                last_error = OrchestratorError(
                    f"{method} {path} -> HTTP {response.status_code}"
                )
            except httpx.HTTPError as exc:
                last_error = exc

            log.warning(
                "orchestrateur %s %s : tentative %s/%s échouée (%s)",
                method,
                path,
                attempt,
                self.retries,
                last_error,
            )
            if attempt < self.retries:
                await asyncio.sleep(min(2 ** (attempt - 1), 5))

        raise OrchestratorError(
            f"orchestrateur injoignable après {self.retries} tentatives : {last_error}"
        )

    async def deploy(self, request: dict) -> dict:
        response = await self._request("POST", "/deployments", json=request)
        if response.status_code >= 400:
            raise OrchestratorError(
                f"orchestrateur a refusé la requête (HTTP {response.status_code}) : "
                f"{response.text[:300]}"
            )
        data = response.json()
        return {
            "deployment_ref": data.get(
                "deployment_ref", f"orch-{request.get('deployment_id')}"
            )
        }

    async def get_deployment(self, deployment_id: int) -> dict:
        response = await self._request("GET", f"/deployments/{deployment_id}")
        if response.status_code == 404:
            return {"status": "unknown", "url": None, "message": "déploiement inconnu"}
        if response.status_code >= 400:
            raise OrchestratorError(
                f"orchestrateur a répondu HTTP {response.status_code}"
            )
        data = response.json()
        return {
            "status": data.get("status", "unknown"),
            "url": data.get("url"),
            "message": data.get("message") or "",
        }

    async def delete_project(self, namespace: str) -> None:
        response = await self._request("DELETE", f"/projects/{namespace}")
        if response.status_code >= 400:
            raise OrchestratorError(
                f"suppression refusée (HTTP {response.status_code}) : {response.text[:300]}"
            )
