import httpx
from app.config import settings


class OrchestratorReal:
    def __init__(self):
        self.base_url = settings.orchestrator_url.rstrip('/')

    async def deploy(self, request: dict) -> dict:
        url = f"{self.base_url}/deployments"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=request)
            resp.raise_for_status()
            data = resp.json()
            return {'deployment_ref': data.get('deployment_ref', f"orch-{request.get('deployment_id')}")}
