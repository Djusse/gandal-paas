import time


class GitLabFake:
    def __init__(self):
        self._next = int(time.time() * 10) % 10000000 + 1
        self.projects = {}
        self.fail_create = False
        self.custom_images = {}


    async def create_project(self, name: str) -> dict:
        if self.fail_create:
            raise RuntimeError("Simulated GitLab creation failure")
        gid = self._next
        self._next += 1
        self.projects[gid] = name
        return {'id': gid, 'web_url': f'http://fake-gitlab/paas/{name}'}

    async def create_webhook(self, gitlab_id: int) -> None:
        return None

    async def list_images(self, gitlab_id: int) -> list[dict]:
        if gitlab_id in self.custom_images:
            return self.custom_images[gitlab_id]
        name = self.projects.get(gitlab_id, 'unknown')
        return [{
            'repository': f'fake-registry/paas/{name}',
            'tag': 'a1b2c3d4',
            'digest': 'sha256:' + '0' * 64
        }]

    async def delete_project(self, gitlab_id: int) -> None:
        self.projects.pop(gitlab_id, None)
