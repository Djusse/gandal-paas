#!/usr/bin/env python3
import sys
import os
import httpx

base_url = os.getenv("BASE_URL", "http://localhost:8000")
secret = os.getenv("WEBHOOK_SECRET", "change-me-long-random")

status = sys.argv[1] if len(sys.argv) > 1 else "running"
project_id = int(sys.argv[2]) if len(sys.argv) > 2 else 1
pipeline_id = int(sys.argv[3]) if len(sys.argv) > 3 else 101
sha = sys.argv[4] if len(sys.argv) > 4 else "a1b2c3d4e5f6"

payload = {
    "object_kind": "pipeline",
    "project": {"id": project_id},
    "object_attributes": {
        "id": pipeline_id,
        "status": status,
        "sha": sha,
        "ref": "main"
    }
}

headers = {
    "X-Gitlab-Token": secret,
    "Content-Type": "application/json"
}

print(f"Sending webhook to {base_url}/webhooks/gitlab with status='{status}'...")
with httpx.Client() as client:
    resp = client.post(f"{base_url}/webhooks/gitlab", json=payload, headers=headers)
    print(f"Response ({resp.status_code}): {resp.text}")
