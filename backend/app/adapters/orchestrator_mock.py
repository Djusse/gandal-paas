import asyncio
import logging
import httpx

from app.config import settings

log = logging.getLogger("orchestrator-mock")


class OrchestratorMock:
    """Orchestrateur de simulation, utilisé quand ``ORCHESTRATOR_MODE=mock``.

    Il rappelle le backend après un court délai, en imitant le vrai service.
    ``get_deployment`` répond toujours ``deployed`` pour que la relance
    périodique n'ait rien à rattraper en développement.
    """

    def __init__(self, callback_delay: float = 3.0):
        self.callback_delay = callback_delay
        self.last_request = None
        self.deployments: dict[int, dict] = {}

    async def deploy(self, request: dict) -> dict:
        log.info("MOCK deploy request: %s", request)
        self.last_request = request
        deployment_id = request['deployment_id']
        url = f"http://{request.get('project', 'mock')}.mock.gandal.local"
        self.deployments[deployment_id] = {
            'status': 'deployed',
            'url': url,
            'message': '',
        }
        asyncio.create_task(self._callback(deployment_id, url))
        return {'deployment_ref': f"mock-{deployment_id}"}

    async def get_deployment(self, deployment_id: int) -> dict:
        return self.deployments.get(
            deployment_id,
            {'status': 'unknown', 'url': None, 'message': 'déploiement inconnu'},
        )

    async def delete_project(self, namespace: str) -> None:
        log.info("MOCK delete namespace: %s", namespace)

    async def _callback(self, deployment_id: int, url: str):
        if self.callback_delay > 0:
            await asyncio.sleep(self.callback_delay)   # pretend Kubernetes is working
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                await c.post(
                    f"{settings.webhook_public_url.rstrip('/')}/internal/deployments/{deployment_id}/status",
                    headers={'X-Internal-Token': settings.internal_token},
                    json={'status': 'deployed', 'url': url, 'message': ''}
                )
        except Exception as e:
            log.warning(
                "Mock callback notice (expected if server callback endpoint not active in test): %s",
                e,
            )
