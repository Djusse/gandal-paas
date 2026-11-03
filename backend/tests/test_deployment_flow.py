"""Tests des corrections R1 (course commit/appel) et de la monotonie du statut."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app import deps
from app.config import settings
from app.models import Deployment, Image, Project
from app.services.deployment_service import (
    DeploymentRecovery,
    is_monotonic,
    send_deployment,
)


# --------------------------------------------------------- monotonie
@pytest.mark.parametrize(
    ("current", "incoming"),
    [
        ("requested", "deploying"),
        ("requested", "deployed"),
        ("requested", "failed"),
        ("deploying", "deployed"),
        ("deploying", "failed"),
        ("deploying", "deploying"),
    ],
)
def test_monotonic_allows_forward_transitions(current, incoming):
    assert is_monotonic(current, incoming) is True


@pytest.mark.parametrize(
    ("current", "incoming"),
    [
        ("deployed", "deploying"),
        ("deployed", "failed"),
        ("failed", "deploying"),
        ("failed", "deployed"),
    ],
)
def test_monotonic_blocks_regressions(current, incoming):
    assert is_monotonic(current, incoming) is False


def test_callback_does_not_overwrite_deployed(client, db_session):
    p = Project(name="mono-app", owner="alice", k8s_namespace="proj-mono-app", status="deploying")
    db_session.add(p)
    db_session.commit()
    img = Image(project_id=p.id, repository="reg/app", tag="v1")
    db_session.add(img)
    db_session.commit()
    dep = Deployment(project_id=p.id, image_id=img.id, status="requested")
    db_session.add(dep)
    db_session.commit()

    headers = {"X-Internal-Token": settings.internal_token}
    first = client.post(
        f"/internal/deployments/{dep.id}/status",
        headers=headers,
        json={"status": "deployed", "url": "http://mono-app.sslip.io"},
    )
    assert first.status_code == 200

    # Appel tardif d'un orchestrateur lent : doit être ignoré.
    late = client.post(
        f"/internal/deployments/{dep.id}/status",
        headers=headers,
        json={"status": "deploying"},
    )
    assert late.status_code == 200
    assert late.json().get("ignored") is True

    db_session.refresh(dep)
    db_session.refresh(p)
    assert dep.status == "deployed"
    assert dep.url == "http://mono-app.sslip.io"
    assert p.status == "deployed"


# -------------------------------------------------- R1 : commit préalable
class RecordingOrchestrator:
    def __init__(self, session_factory):
        self._session_factory = session_factory
        self.seen_status: str | None = None
        self.calls: list[dict] = []

    async def deploy(self, request: dict) -> dict:
        # Au moment de l'appel, la ligne doit déjà être commitée et donc
        # visible depuis une autre session (c'est la correction de R1).
        db = self._session_factory()
        try:
            deployment = db.get(Deployment, request["deployment_id"])
            self.seen_status = deployment.status if deployment else None
        finally:
            db.close()
        self.calls.append(request)
        return {"deployment_ref": f"rec-{request['deployment_id']}"}

    async def get_deployment(self, deployment_id: int) -> dict:
        return {"status": "deployed", "url": "http://late.sslip.io", "message": ""}

    async def delete_project(self, namespace: str) -> None:
        return None


def test_build_success_commits_before_calling_orchestrator(
    client, db_session, session_factory, monkeypatch
):
    import app.services.build_service as bs

    create = client.post("/projects", json={"name": "race-app"}, headers={"X-Dev-User": "alice"})
    assert create.status_code == 201
    project_id = create.json()["id"]
    gitlab_id = create.json()["gitlab_project_id"]

    orchestrator = RecordingOrchestrator(session_factory)
    monkeypatch.setattr(bs, "get_orchestrator", lambda: orchestrator)

    response = client.post(
        "/webhooks/gitlab",
        headers={"X-Gitlab-Token": settings.webhook_secret},
        json={
            "object_kind": "pipeline",
            "project": {"id": gitlab_id},
            "object_attributes": {
                "id": 901,
                "status": "success",
                "sha": "a1b2c3d4e5f6",
                "ref": "main",
            },
        },
    )
    assert response.status_code == 200
    assert len(orchestrator.calls) == 1
    # La ligne était bien commitée (visibilité inter-sessions) et en 'requested'.
    assert orchestrator.seen_status == "requested"

    dep = db_session.query(Deployment).filter_by(project_id=project_id).one()
    assert dep.status == "deploying"
    assert dep.orchestrator_ref == f"rec-{dep.id}"


def test_deploy_request_contract(client, db_session):
    create = client.post("/projects", json={"name": "contract-app"}, headers={"X-Dev-User": "bob"})
    project_id = create.json()["id"]

    p = db_session.get(Project, project_id)
    img = Image(project_id=p.id, repository="reg/app", tag="v1", digest="sha256:" + "1" * 64)
    db_session.add(img)
    db_session.commit()
    dep = Deployment(project_id=p.id, image_id=img.id, status="requested")
    db_session.add(dep)
    db_session.commit()

    orchestrator = RecordingOrchestrator(lambda: db_session)

    import asyncio

    asyncio.run(send_deployment(db_session, orchestrator, p, dep, img))

    request = orchestrator.calls[0]
    assert request["deployment_id"] == dep.id
    assert request["project"] == "contract-app"
    assert request["owner"] == "bob"
    assert request["namespace"] == "proj-contract-app"
    assert request["image"] == "reg/app"
    assert request["tag"] == "v1"
    assert request["digest"].startswith("sha256:")
    assert request["port"] == 8080
    assert request["replicas"] == settings.default_replicas == 2


# ------------------------------------------------------- relance (R11)
def _seed(db_session, name: str, status: str, age_seconds: int):
    p = Project(name=name, owner="alice", k8s_namespace=f"proj-{name}", status="deploying")
    db_session.add(p)
    db_session.commit()
    img = Image(project_id=p.id, repository=f"reg/{name}", tag="v1")
    db_session.add(img)
    db_session.commit()
    dep = Deployment(project_id=p.id, image_id=img.id, status=status)
    dep.created_at = datetime.now() - timedelta(seconds=age_seconds)
    db_session.add(dep)
    db_session.commit()
    return p, dep


def test_recovery_resends_stale_requested(db_session, session_factory):
    p, dep = _seed(db_session, "stale-app", "requested", settings.requested_timeout + 10)
    orchestrator = RecordingOrchestrator(session_factory)
    recovery = DeploymentRecovery(lambda: orchestrator)

    import asyncio

    assert asyncio.run(recovery.recover_once()) == 1
    assert len(orchestrator.calls) == 1
    with session_factory() as check:
        assert check.get(Deployment, dep.id).status == "deploying"


def test_recovery_ignores_recent_requested(db_session, session_factory):
    _seed(db_session, "fresh-app", "requested", 1)
    orchestrator = RecordingOrchestrator(session_factory)
    recovery = DeploymentRecovery(lambda: orchestrator)

    import asyncio

    assert asyncio.run(recovery.recover_once()) == 0
    assert orchestrator.calls == []


def test_recovery_polls_stale_deploying(db_session, session_factory):
    p, dep = _seed(db_session, "late-app", "deploying", settings.deploying_timeout + 10)
    orchestrator = RecordingOrchestrator(session_factory)
    recovery = DeploymentRecovery(lambda: orchestrator)

    import asyncio

    assert asyncio.run(recovery.recover_once()) == 1
    with session_factory() as check:
        refreshed = check.get(Deployment, dep.id)
        assert refreshed.status == "deployed"
        assert refreshed.url == "http://late.sslip.io"
        assert check.get(Project, p.id).status == "deployed"


# ------------------------------------------------------ nommage (R3.3)
@pytest.mark.parametrize("name", ["abc-", "ab", "A-b-c", "a" * 31, "-abc"])
def test_trailing_hyphen_and_bad_names_rejected(client, name):
    response = client.post("/projects", json={"name": name}, headers={"X-Dev-User": "alice"})
    assert response.status_code == 422


def test_valid_names_accepted(client):
    for name in ("abc", "abc-def", "a1b2-c3"):
        response = client.post("/projects", json={"name": name}, headers={"X-Dev-User": "alice"})
        assert response.status_code == 201


# ------------------------------------------------------- suppression
def test_delete_project_removes_rows(client, db_session):
    create = client.post("/projects", json={"name": "gone-app"}, headers={"X-Dev-User": "alice"})
    project_id = create.json()["id"]

    response = client.delete(f"/projects/{project_id}", headers={"X-Dev-User": "alice"})
    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert db_session.get(Project, project_id) is None


def test_delete_project_unknown(client):
    response = client.delete("/projects/9999", headers={"X-Dev-User": "alice"})
    assert response.status_code == 404


def test_deployments_listing(client, db_session):
    create = client.post("/projects", json={"name": "hist-app"}, headers={"X-Dev-User": "alice"})
    project_id = create.json()["id"]

    p = db_session.get(Project, project_id)
    img = Image(project_id=p.id, repository="reg/hist", tag="v1")
    db_session.add(img)
    db_session.commit()
    db_session.add(Deployment(project_id=p.id, image_id=img.id, status="deployed"))
    db_session.commit()

    response = client.get(f"/projects/{project_id}/deployments", headers={"X-Dev-User": "alice"})
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["status"] == "deployed"


def test_gitlab_fake_reset_between_tests():
    assert deps._gl_fake.fail_create is False
