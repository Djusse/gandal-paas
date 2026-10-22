#!/usr/bin/env python3
"""
GANDAL PaaS Backend - End-to-End Demo Script (Fully Faked)
Demonstrates the full developer lifecycle:
1. Student creates a project (POST /projects) -> awaiting_push
2. Student pushes code -> GitLab CI pipeline starts (POST /webhooks/gitlab 'running') -> building
3. Pipeline finishes -> GitLab CI pipeline succeeds (POST /webhooks/gitlab 'success') -> deploying
4. Kubernetes Orchestrator completes deployment -> callback (/internal/deployments/{id}/status) -> deployed
5. Developer checks status & app URL (GET /projects/{id})
"""

import time
import httpx
import sys
import os

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
SECRET = os.getenv("WEBHOOK_SECRET", "change-me-long-random")
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "change-me-long-random")

def print_step(title):
    print("\n" + "=" * 65)
    print(f"  {title}")
    print("=" * 65)

def run_demo():
    print_step("STARTING GANDAL PaaS BACKEND DEMO")
    client = httpx.Client(base_url=BASE_URL, timeout=10.0)

    # 0. Healthcheck
    try:
        health = client.get("/health")
        if health.status_code != 200:
            print(f"Error: API health check failed at {BASE_URL}. Is uvicorn running?")
            sys.exit(1)
        print(f" Connected to PaaS Backend at {BASE_URL}")
    except Exception as e:
        print(f"❌ Failed to reach {BASE_URL}: {e}")
        print("Tip: Run `uvicorn app.main:app --port 8000` in another terminal before running this demo.")
        sys.exit(1)

    # 1. POST /projects as alice
    print_step("Step 1: Student 'alice' creates project 'demo-app'")
    project_payload = {"name": f"demo-app-{int(time.time()) % 10000}", "app_port": 8080}
    headers_alice = {"X-Dev-User": "alice"}
    
    resp = client.post("/projects", json=project_payload, headers=headers_alice)
    if resp.status_code != 201:
        print(f"❌ Failed to create project: {resp.status_code} - {resp.text}")
        sys.exit(1)

    project = resp.json()
    project_id = project["id"]
    gitlab_id = project["gitlab_project_id"]
    print(f" Project created successfully!")
    print(f"  - Project ID:         {project['id']}")
    print(f"  - Name:               {project['name']}")
    print(f"  - Owner:              {project['owner']}")
    print(f"  - Status:             {project['status']}")
    print(f"  - Git Repository URL: {project['repo_url']}")
    print(f"  - K8s Namespace:      {project['k8s_namespace']}")
    print(f"  - Container Port:     {project['app_port']}")

    # 2. Pipeline Running
    pipeline_id = int(time.time())
    print_step(f"Step 2: Student pushes code -> Pipeline starts (Webhook 'running', Pipeline #{pipeline_id})")
    webhook_headers = {"X-Gitlab-Token": SECRET}
    running_payload = {
        "object_kind": "pipeline",
        "project": {"id": gitlab_id},
        "object_attributes": {
            "id": pipeline_id,
            "status": "running",
            "sha": "a1b2c3d4e5f67890",
            "ref": "main"
        }
    }

    resp = client.post("/webhooks/gitlab", json=running_payload, headers=webhook_headers)
    print(f" Webhook received: {resp.json()}")

    p_status = client.get(f"/projects/{project_id}", headers=headers_alice).json()
    print(f" Current Project Status: [{p_status['status']}] (Expected: building)")

    # 3. Pipeline Success
    print_step(f"Step 3: Pipeline succeeds -> Image in Registry -> Deploy requested (Pipeline #{pipeline_id})")
    success_payload = {
        "object_kind": "pipeline",
        "project": {"id": gitlab_id},
        "object_attributes": {
            "id": pipeline_id,
            "status": "success",
            "sha": "a1b2c3d4e5f67890",
            "ref": "main"
        }
    }

    resp = client.post("/webhooks/gitlab", json=success_payload, headers=webhook_headers)
    print(f" Webhook received: {resp.json()}")

    time.sleep(0.5)
    p_status = client.get(f"/projects/{project_id}", headers=headers_alice).json()
    print(f" Current Project Status: [{p_status['status']}] (Expected: deploying)")

    # 4. Wait for Mock Orchestrator Callback (approx 3s)
    print_step("Step 4: Waiting for Orchestrator to deploy on Kubernetes (approx 3s)...")
    p_status = {}
    for i in range(10):
        time.sleep(0.5)
        p_status = client.get(f"/projects/{project_id}", headers=headers_alice).json()
        if p_status.get('status') == 'deployed':
            print(f"  Received Orchestrator callback at {i * 0.5:.1f}s!")
            break
        print(f"  Deploying... ({p_status.get('status')})")

    print(f" Final Project Status: [{p_status.get('status')}] (Expected: deployed)")


    # 5. Review full project resources
    print_step("Step 5: Querying Developer Portal Views")
    
    images = client.get(f"/projects/{project_id}/images", headers=headers_alice).json()
    print(f"\n Built Images ({len(images)}):")
    for img in images:
        print(f"  - ID {img['id']}: {img['repository']}:{img['tag']} (digest: {img['digest'][:16]}...)")

    builds = client.get(f"/projects/{project_id}/builds", headers=headers_alice).json()
    print(f"\n Pipeline Events ({len(builds)}):")
    for b in builds:
        print(f"  - Pipeline #{b['pipeline_id']}: status '{b['status']}' at commit {b['sha'][:8]}")

    print_step("DEMO COMPLETED SUCCESSFULLY! ")
    print(f"Swagger API Documentation: {BASE_URL}/docs")
    print(f"OpenAPI Schema URL:        {BASE_URL}/openapi.json")

if __name__ == "__main__":
    run_demo()
