import httpx
from app.config import settings


class GitLabReal:
    def __init__(self):
        self.base_url = settings.gitlab_url.rstrip('/') + '/api/v4'
        self.headers = {'PRIVATE-TOKEN': settings.gitlab_token}
        self.verify = settings.gitlab_ca_bundle if settings.gitlab_ca_bundle else True

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, headers=self.headers, verify=self.verify, timeout=10.0)

    async def create_project(self, name: str) -> dict:
        payload = {
            'name': name,
            'path': name,
            'initialize_with_readme': False,
            'ci_config_path': settings.ci_template,
        }
        if settings.gitlab_group_id:
            payload['namespace_id'] = settings.gitlab_group_id

        async with self._client() as client:
            resp = await client.post('/projects', json=payload)
            resp.raise_for_status()
            data = resp.json()
            return {'id': data['id'], 'web_url': data['web_url']}

    async def create_webhook(self, gitlab_id: int) -> None:
        webhook_url = f"{settings.webhook_public_url.rstrip('/')}/webhooks/gitlab"
        payload = {
            'url': webhook_url,
            'token': settings.webhook_secret,
            'pipeline_events': True,
            'push_events': False,
            'enable_ssl_verification': True if settings.gitlab_ca_bundle else False,
        }
        async with self._client() as client:
            resp = await client.post(f'/projects/{gitlab_id}/hooks', json=payload)
            resp.raise_for_status()

    async def list_images(self, gitlab_id: int) -> list[dict]:
        results = []
        async with self._client() as client:
            # 1. Get registry repositories for this project
            resp = await client.get(f'/projects/{gitlab_id}/registry/repositories')
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            repos = resp.json()

            for repo in repos:
                repo_id = repo['id']
                repo_location = repo['location']

                # 2. Get tags for the repository
                tags_resp = await client.get(f'/projects/{gitlab_id}/registry/repositories/{repo_id}/tags')
                if tags_resp.status_code == 404:
                    continue
                tags_resp.raise_for_status()
                tags = tags_resp.json()

                for tag in tags:
                    tag_name = tag['name']
                    # 3. Get tag detail to retrieve digest
                    tag_detail_resp = await client.get(
                        f'/projects/{gitlab_id}/registry/repositories/{repo_id}/tags/{tag_name}'
                    )
                    digest = None
                    if tag_detail_resp.status_code == 200:
                        tag_detail = tag_detail_resp.json()
                        digest = tag_detail.get('digest')

                    results.append({
                        'repository': repo_location,
                        'tag': tag_name,
                        'digest': digest
                    })
        return results

    async def delete_project(self, gitlab_id: int) -> None:
        async with self._client() as client:
            resp = await client.delete(f'/projects/{gitlab_id}')
            if resp.status_code != 404:
                resp.raise_for_status()
