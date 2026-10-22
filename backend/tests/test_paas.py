import pytest
from app.config import settings
from app import deps
from app.models import Project, Deployment, Image


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_auth_required_in_dev_mode(client):
    # Missing X-Dev-User header returns 401
    resp = client.post("/projects", json={"name": "demo"})
    assert resp.status_code == 401


def test_case_1_create_project_succeeds(client):
    resp = client.post(
        "/projects",
        json={"name": "my-app", "app_port": 3000},
        headers={"X-Dev-User": "alice"}
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "my-app"
    assert data["owner"] == "alice"
    assert data["status"] == "awaiting_push"
    assert data["repo_url"] == "http://fake-gitlab/paas/my-app"
    assert data["gitlab_project_id"] == 1
    assert data["k8s_namespace"] == "proj-my-app"
    assert data["app_port"] == 3000


def test_case_2_invalid_and_duplicate_name(client):
    # Invalid names (regex pattern: ^[a-z][a-z0-9-]{2,29}$)
    resp = client.post("/projects", json={"name": "Bad_Name"}, headers={"X-Dev-User": "alice"})
    assert resp.status_code == 422

    resp = client.post("/projects", json={"name": "ab"}, headers={"X-Dev-User": "alice"})
    assert resp.status_code == 422

    resp = client.post("/projects", json={"name": "1badstart"}, headers={"X-Dev-User": "alice"})
    assert resp.status_code == 422

    # Valid name
    resp = client.post("/projects", json={"name": "valid-app"}, headers={"X-Dev-User": "alice"})
    assert resp.status_code == 201

    # Duplicate name returns 409 Conflict
    resp_dup = client.post("/projects", json={"name": "valid-app"}, headers={"X-Dev-User": "alice"})
    assert resp_dup.status_code == 409


def test_user_isolation(client):
    # Alice creates project
    resp = client.post("/projects", json={"name": "alice-proj"}, headers={"X-Dev-User": "alice"})
    assert resp.status_code == 201
    proj_id = resp.json()["id"]

    # Bob cannot view alice's project -> returns 404
    resp_bob = client.get(f"/projects/{proj_id}", headers={"X-Dev-User": "bob"})
    assert resp_bob.status_code == 404

    # Alice can view her own project
    resp_alice = client.get(f"/projects/{proj_id}", headers={"X-Dev-User": "alice"})
    assert resp_alice.status_code == 200
    assert resp_alice.json()["id"] == proj_id


def test_case_3_webhook_bad_token(client):
    resp = client.post(
        "/webhooks/gitlab",
        headers={"X-Gitlab-Token": "bad-secret-token"},
        json={"object_kind": "pipeline"}
    )
    assert resp.status_code == 401


def test_case_4_pipeline_success_creates_image_and_deployment(client, db_session):
    # 1. Create project
    create_resp = client.post(
        "/projects",
        json={"name": "order-service"},
        headers={"X-Dev-User": "alice"}
    )
    assert create_resp.status_code == 201
    proj_id = create_resp.json()["id"]
    gitlab_id = create_resp.json()["gitlab_project_id"]

    # 2. Pipeline 'running' webhook
    resp_running = client.post(
        "/webhooks/gitlab",
        headers={"X-Gitlab-Token": settings.webhook_secret},
        json={
            "object_kind": "pipeline",
            "project": {"id": gitlab_id},
            "object_attributes": {
                "id": 200,
                "status": "running",
                "sha": "a1b2c3d4e5f6",
                "ref": "main"
            }
        }
    )
    assert resp_running.status_code == 200
    p = db_session.get(Project, proj_id)
    assert p.status == "building"

    # 3. Pipeline 'success' webhook
    resp_success = client.post(
        "/webhooks/gitlab",
        headers={"X-Gitlab-Token": settings.webhook_secret},
        json={
            "object_kind": "pipeline",
            "project": {"id": gitlab_id},
            "object_attributes": {
                "id": 200,
                "status": "success",
                "sha": "a1b2c3d4e5f6",
                "ref": "main"
            }
        }
    )
    assert resp_success.status_code == 200

    # 4. Check images and deployments created
    images = db_session.query(Image).filter_by(project_id=proj_id).all()
    assert len(images) == 1
    assert images[0].tag == "a1b2c3d4"
    assert images[0].repository == "fake-registry/paas/order-service"

    deployments = db_session.query(Deployment).filter_by(project_id=proj_id).all()
    assert len(deployments) == 1
    assert deployments[0].image_id == images[0].id
    assert deployments[0].orchestrator_ref.startswith("mock-")


def test_case_5_webhook_duplicate_protection(client, db_session):
    create_resp = client.post(
        "/projects",
        json={"name": "idempotent-app"},
        headers={"X-Dev-User": "alice"}
    )
    gitlab_id = create_resp.json()["gitlab_project_id"]
    proj_id = create_resp.json()["id"]

    webhook_payload = {
        "object_kind": "pipeline",
        "project": {"id": gitlab_id},
        "object_attributes": {
            "id": 300,
            "status": "success",
            "sha": "a1b2c3d4e5f6",
            "ref": "main"
        }
    }

    # First delivery
    r1 = client.post("/webhooks/gitlab", headers={"X-Gitlab-Token": settings.webhook_secret}, json=webhook_payload)
    assert r1.status_code == 200
    assert r1.json() == {"ok": True}

    # Duplicate delivery
    r2 = client.post("/webhooks/gitlab", headers={"X-Gitlab-Token": settings.webhook_secret}, json=webhook_payload)
    assert r2.status_code == 200
    assert r2.json() == {"duplicate": True}

    # Verify only 1 deployment created
    deployments = db_session.query(Deployment).filter_by(project_id=proj_id).all()
    assert len(deployments) == 1


def test_case_6_gitlab_failure_rolls_back_and_marks_project_failed(client, db_session):
    deps._gl_fake.fail_create = True
    with pytest.raises(Exception):
        client.post(
            "/projects",
            json={"name": "fail-app"},
            headers={"X-Dev-User": "alice"}
        )

    # Check project state in DB
    p = db_session.query(Project).filter_by(name="fail-app").first()
    assert p is not None
    assert p.status == "failed"
    assert "Simulated GitLab creation failure" in (p.error or "")


def test_case_7_internal_callback_auth_and_status(client, db_session):
    # Setup project and deployment
    p = Project(name="callback-app", owner="alice", k8s_namespace="proj-callback-app", status="deploying")
    db_session.add(p)
    db_session.commit()

    img = Image(project_id=p.id, repository="reg/app", tag="v1.0")
    db_session.add(img)
    db_session.commit()

    dep = Deployment(project_id=p.id, image_id=img.id, status="requested")
    db_session.add(dep)
    db_session.commit()

    # Wrong internal token -> 401
    resp_bad = client.post(
        f"/internal/deployments/{dep.id}/status",
        headers={"X-Internal-Token": "wrong-secret"},
        json={"status": "deployed", "url": "http://app.gandal.local"}
    )
    assert resp_bad.status_code == 401

    # Valid internal token -> 200 and project becomes deployed
    resp_ok = client.post(
        f"/internal/deployments/{dep.id}/status",
        headers={"X-Internal-Token": settings.internal_token},
        json={"status": "deployed", "url": "http://callback-app.apps.gandal.local", "message": "Success"}
    )
    assert resp_ok.status_code == 200

    db_session.refresh(dep)
    db_session.refresh(p)
    assert dep.status == "deployed"
    assert dep.url == "http://callback-app.apps.gandal.local"
    assert p.status == "deployed"
    assert p.error is None


def test_internal_callback_failure_updates_project_to_failed(client, db_session):
    p = Project(name="fail-deploy", owner="alice", k8s_namespace="proj-fail", status="deploying")
    db_session.add(p)
    db_session.commit()

    img = Image(project_id=p.id, repository="reg/fail", tag="v1.0")
    db_session.add(img)
    db_session.commit()

    dep = Deployment(project_id=p.id, image_id=img.id, status="requested")
    db_session.add(dep)
    db_session.commit()

    resp = client.post(
        f"/internal/deployments/{dep.id}/status",
        headers={"X-Internal-Token": settings.internal_token},
        json={"status": "failed", "message": "CrashLoopBackOff"}
    )
    assert resp.status_code == 200

    db_session.refresh(dep)
    db_session.refresh(p)
    assert dep.status == "failed"
    assert dep.message == "CrashLoopBackOff"
    assert p.status == "failed"
    assert p.error == "CrashLoopBackOff"
