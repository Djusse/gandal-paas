"""Tests du service HTTP de l'orchestrateur et de la réconciliation."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from gandal.k8s import STATUS_DEPLOYED
from gandal.notifier import BackendNotifier
from gandal.service import DeploymentService

AUTH = {"X-Orchestrator-Token": "test-token"}


class RecordingNotifier:
    """Notifier factice : enregistre les rappels au lieu de les envoyer."""

    def __init__(self, succeed: bool = True):
        self.succeed = succeed
        self.calls: list[tuple] = []

    async def send_status(self, deployment_id, status, url=None, message=""):
        self.calls.append((deployment_id, status, url, message))
        return self.succeed


@pytest.fixture
def service(backend, cfg):
    notifier = RecordingNotifier()
    return DeploymentService(backend=backend, notifier=notifier, cfg=cfg)


@pytest.fixture
def client(backend, service):
    from app.main import app

    app.state.deployment_service = service
    app.state.kubernetes_ready = True
    with TestClient(app) as test_client:
        yield test_client
    app.state.deployment_service = None


# ------------------------------------------------------------- endpoints
def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["kubernetes"] is True


def test_deploy_requires_token(client, payload):
    response = client.post("/deployments", json=payload)
    assert response.status_code == 401

    response = client.post(
        "/deployments", json=payload, headers={"X-Orchestrator-Token": "faux"}
    )
    assert response.status_code == 401


def test_deploy_accepts_valid_request(client, payload, store):
    response = client.post("/deployments", json=payload, headers=AUTH)
    assert response.status_code == 202
    body = response.json()
    assert body["deployment_ref"] == "orch-42"
    assert body["status"] == "deploying"
    assert body["url"] == "http://mon-app.sslip.io"
    assert ("deployment", "proj-mon-app", "mon-app") in store.objects


def test_deploy_is_idempotent(client, payload, store):
    client.post("/deployments", json=payload, headers=AUTH)
    client.post("/deployments", json=payload, headers=AUTH)

    deployments = store.deployments()
    assert len(deployments) == 1


@pytest.mark.parametrize("namespace", ["kube-system", "proj-autre-app", "autre-namespace"])
def test_deploy_refuses_bad_namespace(client, payload, namespace):
    response = client.post(
        "/deployments", json=dict(payload, namespace=namespace), headers=AUTH
    )
    assert response.status_code == 422
    assert "namespace" in response.json()["detail"]


def test_deploy_refuses_invalid_name(client, payload):
    response = client.post(
        "/deployments",
        json=dict(payload, project="Mon_App", namespace="proj-Mon_App"),
        headers=AUTH,
    )
    assert response.status_code == 422


def test_get_deployment_reads_kubernetes(client, payload, store):
    client.post("/deployments", json=payload, headers=AUTH)

    store.set_ready(0)
    response = client.get("/deployments/42", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["status"] == "deploying"

    store.set_ready(2)
    response = client.get("/deployments/42", headers=AUTH)
    assert response.json()["status"] == STATUS_DEPLOYED
    assert response.json()["url"] == "http://mon-app.sslip.io"


def test_get_unknown_deployment(client):
    response = client.get("/deployments/999", headers=AUTH)
    assert response.status_code == 404


def test_delete_project(client, payload, store):
    client.post("/deployments", json=payload, headers=AUTH)

    response = client.delete("/projects/proj-mon-app", headers=AUTH)
    assert response.status_code == 202
    assert store.deleted_namespaces == ["proj-mon-app"]


def test_delete_reserved_namespace(client):
    response = client.delete("/projects/kube-system", headers=AUTH)
    assert response.status_code == 422


# ------------------------------------------------------- réconciliation
def test_reconcile_reports_deployed(service, backend, payload):
    from gandal.k8s import DeploySpec

    backend.apply(DeploySpec.from_payload(payload, backend.cfg))
    assert backend.state_of(backend.read_deployment(42)).status == STATUS_DEPLOYED

    sent = asyncio.run(service.reconcile_once())

    assert sent == 1
    assert service.notifier.calls[0][:2] == (42, STATUS_DEPLOYED)
    # L'annotation évite un second rappel.
    assert asyncio.run(service.reconcile_once()) == 0


def test_reconcile_retries_when_callback_fails(service, backend, payload):
    from gandal.k8s import DeploySpec

    backend.apply(DeploySpec.from_payload(payload, backend.cfg))
    service.notifier.succeed = False

    assert asyncio.run(service.reconcile_once()) == 0
    assert service.notifier.calls  # une tentative a bien eu lieu

    service.notifier.succeed = True
    assert asyncio.run(service.reconcile_once()) == 1


def test_reconcile_reports_failure(service, backend, payload, store):
    from gandal.k8s import DeploySpec

    backend.apply(DeploySpec.from_payload(payload, backend.cfg))
    store.set_ready(0)
    store.age(timedelta(seconds=backend.cfg.rollout_timeout + 5))

    assert asyncio.run(service.reconcile_once()) == 1
    assert service.notifier.calls[0][1] == "failed"


def test_reconcile_ignores_unmanaged_deployments(service, backend, payload, store):
    from gandal.k8s import DeploySpec

    backend.apply(DeploySpec.from_payload(payload, backend.cfg))
    deployment = store.deployments()[("deployment", "proj-mon-app", "mon-app")]
    deployment["metadata"]["labels"].pop("gandal.io/managed")

    assert asyncio.run(service.reconcile_once()) == 0
    assert service.notifier.calls == []


# ------------------------------------------------------------- notifier
def test_notifier_sends_token_and_payload(cfg):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["token"] = request.headers.get("X-Internal-Token")
        seen["body"] = request.content
        return httpx.Response(200, json={"ok": True})

    notifier = BackendNotifier(cfg, transport=httpx.MockTransport(handler))
    delivered = asyncio.run(
        notifier.send_status(42, "deployed", "http://mon-app.sslip.io", "")
    )

    assert delivered is True
    assert seen["token"] == "test-internal"
    assert seen["url"] == "http://backend.test/internal/deployments/42/status"
    assert b'"deployed"' in seen["body"]


def test_notifier_returns_false_on_error(cfg):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    notifier = BackendNotifier(cfg, transport=httpx.MockTransport(handler))
    assert asyncio.run(notifier.send_status(42, "failed")) is False
