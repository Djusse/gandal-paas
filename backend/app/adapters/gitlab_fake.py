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

    async def list_images(self, gitlab_id: int, sha: str | None = None) -> list[dict]:
        """Images simulées pour un projet.

        Le tag suit la convention du pipeline réel : ``CI_COMMIT_SHORT_SHA``,
        soit les 8 premiers caractères du SHA. Cela permet de publier une image
        dans le registry du cluster sous ce tag et de la déployer réellement
        (``GITLAB_FAKE_TAG`` fixe la valeur si on préfère, mais un SHA différent
        ne la trouverait pas).
        """
        from app.config import settings

        if gitlab_id in self.custom_images:
            return self.custom_images[gitlab_id]

        name = self.projects.get(gitlab_id, 'unknown')
        repository = settings.gitlab_fake_repository or (
            f"{settings.gitlab_fake_registry.rstrip('/')}/{name}"
        )
        tag = settings.gitlab_fake_tag or (sha or 'a1b2c3d4')[:8]
        return [{
            'repository': repository,
            'tag': tag,
            # Un digest vide évite d'épingler une image inexistante : le tag est
            # alors utilisé, ce qui est nécessaire avec le registry du cluster.
            'digest': settings.gitlab_fake_digest or None,
        }]

    async def delete_project(self, gitlab_id: int) -> None:
        self.projects.pop(gitlab_id, None)
