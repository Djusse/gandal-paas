import asyncio
import logging
import httpx
from app.config import settings

log = logging.getLogger("orchestrator-mock")


class OrchestratorMock:
    def __init__(self, callback_delay: float = 3.0):
        self.callback_delay = callback_delay
        self.last_request = None

    async def deploy(self, request: dict) -> dict:
        log.info("MOCK deploy request: %s", request)
        self.last_request = request
        deployment_id = request['deployment_id']
        asyncio.create_task(self._callback(deployment_id))
        return {'deployment_ref': f"mock-{deployment_id}"}

    async def _callback(self, deployment_id: int):
        if self.callback_delay > 0:
            await asyncio.sleep(self.callback_delay)   # pretend Kubernetes is working
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                await c.post(
                    f"{settings.webhook_public_url.rstrip('/')}/internal/deployments/{deployment_id}/status",
                    headers={'X-Internal-Token': settings.internal_token},
                    json={'status': 'deployed', 'url': f'http://mock.gandal.local', 'message': ''}
                )
        except Exception as e:
            log.warning("Mock callback notice (expected if server callback endpoint not active in test): %s", e)
