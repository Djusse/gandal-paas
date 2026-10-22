from typing import Protocol


class GitLabPort(Protocol):
    async def create_project(self, name: str) -> dict: ...      # {'id': int, 'web_url': str}
    async def create_webhook(self, gitlab_id: int) -> None: ...
    async def list_images(self, gitlab_id: int) -> list[dict]: ...  # [{'repository', 'tag', 'digest'}]
    async def delete_project(self, gitlab_id: int) -> None: ...


class OrchestratorPort(Protocol):
    async def deploy(self, request: dict) -> dict: ...          # {'deployment_ref': str}
