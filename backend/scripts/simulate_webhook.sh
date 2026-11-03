#!/usr/bin/env bash
set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
WEBHOOK_SECRET="${WEBHOOK_SECRET:-change-me-long-random}"
STATUS="${1:-running}"
PROJECT_ID="${2:-1}"
PIPELINE_ID="${3:-101}"
SHA="${4:-a1b2c3d4e5f6}"

echo "Sending pipeline event '$STATUS' for project $PROJECT_ID (pipeline $PIPELINE_ID, sha $SHA)..."

curl -X POST "${BASE_URL}/webhooks/gitlab" \
  -H "X-Gitlab-Token: ${WEBHOOK_SECRET}" \
  -H "Content-Type: application/json" \
  -d '{
    "object_kind": "pipeline",
    "project": {"id": '"${PROJECT_ID}"'},
    "object_attributes": {
      "id": '"${PIPELINE_ID}"',
      "status": "'"${STATUS}"'",
      "sha": "'"${SHA}"'",
      "ref": "main"
    }
  }'

echo ""
