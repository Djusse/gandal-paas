from fastapi import Header, HTTPException, Depends
import httpx
from app.config import settings
from app.adapters.gitlab_fake import GitLabFake
from app.adapters.orchestrator_mock import OrchestratorMock

_gl_fake = GitLabFake()
_orch_mock = OrchestratorMock()

def get_gitlab():
    if settings.gitlab_mode == 'real':
        from app.adapters.gitlab_real import GitLabReal
        return GitLabReal()
    return _gl_fake

def get_orchestrator():
    if settings.orchestrator_mode == 'real':
        from app.adapters.orchestrator_real import OrchestratorReal
        return OrchestratorReal()
    return _orch_mock

async def get_current_user(
    x_dev_user: str | None = Header(default=None, alias="X-Dev-User"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> str:
    if settings.auth_mode == 'dev':
        if not x_dev_user:
            raise HTTPException(status_code=401, detail="Dev authentication requires X-Dev-User header")
        return x_dev_user.strip()

    elif settings.auth_mode == 'oauth':
        token = None
        if authorization and authorization.startswith("Bearer "):
            token = authorization.split("Bearer ", 1)[1].strip()

        if not token:
            raise HTTPException(status_code=401, detail="OAuth authentication requires Bearer token")

        # Validate with GitLab OAuth / API
        try:
            gl_url = settings.gitlab_url.rstrip('/') + '/api/v4/user'
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(gl_url, headers={"Authorization": f"Bearer {token}"})
                if resp.status_code != 200:
                    raise HTTPException(status_code=401, detail="Invalid GitLab OAuth token")
                data = resp.json()
                return data.get("username", "oauth_user")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"OAuth verification failed: {e}")

    else:
        raise HTTPException(status_code=500, detail=f"Unsupported auth mode: {settings.auth_mode}")
