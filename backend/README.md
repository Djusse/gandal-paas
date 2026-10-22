# GANDAL PaaS Backend (FastAPI)

> **Central Control Plane for GANDAL PaaS**: Connects the Developer Portal, private GitLab, CI/CD Container Registry, and the Kubernetes Deployment Orchestrator.

---

## 1. Simple Terms: How Does It Work?

Imagine you are running a university cloud platform (PaaS) where students write code, and the platform runs it on a cluster automatically without students needing to learn Kubernetes or CI pipelines.

```mermaid
sequenceDiagram
    autonumber
    actor Student as Student / Dev Portal
    participant API as PaaS Backend (Our Service)
    participant GitLab as Private GitLab
    participant Runner as CI/CD Runner VM
    participant Registry as Container Registry
    participant Orch as K8s Orchestrator

    Student->>API: 1. POST /projects {"name": "my-app"}
    API->>GitLab: 2. Create empty repo & register pipeline webhook & shared CI template
    API-->>Student: 3. Return repo_url (Status: awaiting_push)
    
    Student->>GitLab: 4. git push origin main
    GitLab->>Runner: 5. Trigger shared CI build (Kaniko)
    GitLab->>API: 6. Webhook: Pipeline 'running' (Status: building)
    Runner->>Registry: 7. Build container image & push (tag = git commit short SHA)
    GitLab->>API: 8. Webhook: Pipeline 'success' (Status: built)
    
    API->>Registry: 9. Locate image & immutable digest
    API->>Orch: 10. POST /deployments (project, image, port, replicas)
    Note over API: Status: deploying
    Orch->>API: 11. Callback /internal/deployments/{id}/status (deployed, URL)
    Note over API: Status: deployed
    Student->>API: 12. GET /projects/{id} -> Sees app URL!
```

### The 4 Core Actors
1. **The Student (Developer Portal)**:
   - Asks for a project name (e.g. `my-app`).
   - Receives an empty Git repository URL.
   - Pushes code (`git push origin main`).
   - Watches progress in the portal (`awaiting_push` ➔ `building` ➔ `deploying` ➔ `deployed`).
2. **GitLab & CI/CD**:
   - The student pushes code.
   - A shared CI template (`templates/build.yml@paas/ci-templates`) runs on a dedicated runner VM using Kaniko (no Docker socket mounted for tenant security).
   - Once the image is built and pushed to the container registry, GitLab fires a webhook to our PaaS backend.
3. **PaaS Backend (This Repository)**:
   - The "brain" and coordinator.
   - Manages metadata in PostgreSQL (projects, pipeline events, images, deployments).
   - Listens to webhooks securely with idempotent deduplication.
   - Looks up the built image digest in the registry.
   - Instructs the Orchestrator to deploy.
4. **Kubernetes Orchestrator**:
   - Deploys the container to the student's isolated Kubernetes namespace (`proj-{name}`).
   - Sets up Kubernetes Service, Ingress / Gateway API route, and DNS.
   - Calls our Backend callback with the live public URL (`http://{name}.apps.gandal.local`).

---

## 2. Ports and Adapters: Developing while other teams finish

The backend never talks directly to external systems inside business logic. All external integrations are defined as **Protocols (Ports)** with **swappable Adapters**:

| Dependency | Owner | In Development | In Production | Switch Env Var |
|---|---|---|---|---|
| **GitLab & Registry** | GitLab team | `GitLabFake` (in-memory) | `GitLabReal` (v4 REST API) | `GITLAB_MODE=fake\|real` |
| **CI Runner & Template** | CI/CD team | `scripts/simulate_webhook.py` | Real GitLab Runner VM | *(none, push-driven)* |
| **Orchestrator** | Orchestrator team | `OrchestratorMock` (async callback) | `OrchestratorReal` (HTTP POST) | `ORCHESTRATOR_MODE=mock\|real` |
| **Authentication** | GitLab team | `X-Dev-User` dev header | GitLab OAuth Bearer token | `AUTH_MODE=dev\|oauth` |
| **Kubernetes / Infra** | Infra team | Not queried (Orchestrator owns it)| Orchestrator handles K8s | *(none)* |

Switching any component from fake to real requires **only changing an environment variable**, never touching business logic or routers!

---

## 3. Directory Structure

```
paas-backend/
├── app/
│   ├── main.py                     # FastAPI application setup & routing
│   ├── config.py                   # Pydantic Settings configuration & env loading
│   ├── db.py                       # SQLAlchemy database engine & session dependency
│   ├── models.py                   # ORM models (Project, PipelineEvent, Image, Deployment)
│   ├── schemas.py                  # Pydantic request/response schemas & validation
│   ├── ports.py                    # Protocols for GitLabPort and OrchestratorPort
│   ├── deps.py                     # Dependencies & adapter injection (fake/real switches)
│   ├── adapters/
│   │   ├── gitlab_fake.py          # In-memory fake GitLab & Registry
│   │   ├── gitlab_real.py          # Real GitLab v4 REST client
│   │   ├── orchestrator_mock.py    # Mock Orchestrator simulating async K8s deploy
│   │   └── orchestrator_real.py    # Real Orchestrator client (POST /deployments)
│   ├── routers/
│   │   ├── health.py               # GET /health
│   │   ├── projects.py             # CRUD & user endpoints for projects
│   │   ├── webhooks.py             # POST /webhooks/gitlab (HMAC-verified, deduplicated)
│   │   └── internal.py             # POST /internal/deployments/{id}/status (token-protected)
│   └── services/
│       ├── project_service.py      # Project lifecycle & tenant authorization
│       └── build_service.py        # Background task for registry lookup & deployment
├── alembic/                        # Database migration scripts
├── tests/
│   ├── conftest.py                 # SQLite in-memory test database & client fixtures
│   └── test_paas.py                # Comprehensive test suite covering all 7+ checkpoints
├── scripts/
│   ├── simulate_webhook.sh         # Bash webhook simulator
│   ├── simulate_webhook.py         # Cross-platform Python webhook simulator
│   └── demo.py                     # Automated end-to-end lifecycle demo
├── Dockerfile                      # Production container image
├── docker-compose.yml              # PostgreSQL + API container composition
├── openapi.json                    # Exported OpenAPI 3.1 specification
├── requirements.txt                # Python dependencies
├── .env.example                    # Template environment variables
└── .env                            # Active environment configuration
```

---

## 4. Quickstart: Running Locally

### Prerequisites
- Python 3.12+ (Python 3.14 compatible)
- (Optional) Docker & Docker Compose for PostgreSQL container

### Option A: Local Dev Server
```powershell
# 1. Activate virtual environment
.venv\Scripts\activate   # On Linux/macOS: source .venv/bin/activate

# 2. Run migrations
alembic upgrade head

# 3. Start the API
uvicorn app.main:app --reload --port 8000
```

### Option B: Run via Docker Compose
```bash
docker compose up -d
```

### Option C: Run the Full End-to-End Demo
With the server running on `http://localhost:8000`:
```powershell
python scripts/demo.py
```

### Option D: Run Test Suite
```powershell
pytest -q
```
*Result: 11 passed in ~2 seconds.*

---

## 5. API Endpoints Overview

| Method | Path | Auth Header | Description |
|---|---|---|---|
| `GET` | `/health` | *None* | Health check (`{"status": "ok"}`) |
| `POST` | `/projects` | `X-Dev-User: <username>` | Create new project (returns `awaiting_push` & `repo_url`) |
| `GET` | `/projects` | `X-Dev-User: <username>` | List only caller's projects |
| `GET` | `/projects/{id}` | `X-Dev-User: <username>` | Get project details (404 if not owner) |
| `GET` | `/projects/{id}/builds` | `X-Dev-User: <username>` | List pipeline events for project |
| `GET` | `/projects/{id}/images` | `X-Dev-User: <username>` | List built container images & tags |
| `POST` | `/projects/{id}/deploy` | `X-Dev-User: <username>` | Manual redeploy or rollback to specific image |
| `POST` | `/webhooks/gitlab` | `X-Gitlab-Token: <secret>` | Receives pipeline events, triggers build handler |
| `POST` | `/internal/deployments/{id}/status` | `X-Internal-Token: <token>` | Orchestrator deployment completion callback |

Swagger interactive documentation is available at `http://localhost:8000/docs`.

---

## 6. Project Status Lifecycle

```
[creating] ──> [awaiting_push] ──> [building] ──> [built] ──> [deploying] ──> [deployed]
      │                               │                              │
      └──> [failed]                   └──> [build_failed]            └──> [failed]
```
- **`creating`**: Initial row saved in DB; backend is currently creating the GitLab repo and webhook.
- **`awaiting_push`**: Repository created, empty, with `ci_config_path` pointing to shared template. Waiting for student's first push.
- **`building`**: GitLab CI pipeline received `pending` or `running` webhook.
- **`built`**: GitLab CI pipeline succeeded. Image is published in container registry.
- **`deploying`**: Backend matched commit SHA to registry image digest and requested Orchestrator to deploy.
- **`deployed`**: Orchestrator successfully deployed pods and ingress on Kubernetes and called status callback.
- **Failure states**:
  - `build_failed`: Pipeline failed in GitLab CI (e.g. Dockerfile build error or student tests failed). A new `git push` automatically restarts the cycle at `building`.
  - `failed`: GitLab repo creation error, missing image in registry, or Orchestrator deployment error. Details stored in `project.error`.

---

## 7. Team-by-Team Integration Runbook (Step 13)

Switch one dependency at a time and re-run `python scripts/demo.py`:

### A. Switching GitLab to Real
1. Update `.env`:
   ```ini
   GITLAB_MODE=real
   GITLAB_URL=https://gitlab.gandal.local
   GITLAB_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx
   GITLAB_GROUP_ID=42
   GITLAB_CA_BUNDLE=/etc/ssl/certs/gandal-ca.pem
   ```
2. Verify token access:
   ```bash
   curl -k -H "PRIVATE-TOKEN: $GITLAB_TOKEN" "$GITLAB_URL/api/v4/user"
   ```
3. Create a test project via `POST /projects` and verify the repository appears in the group without README, has the webhook pointing to `$WEBHOOK_PUBLIC_URL/webhooks/gitlab`, and has `ci_config_path` set.
4. Push a sample app with a `Dockerfile`. Confirm webhook arrives and updates project to `building` then `built`.

### B. Runner & CI Template
- Ensure template project exists at `$CI_TEMPLATE` (e.g. `templates/build.yml@paas/ci-templates`).
- Template must build using Kaniko:
  ```yaml
  /kaniko/executor --context $CI_PROJECT_DIR --dockerfile $CI_PROJECT_DIR/Dockerfile --destination $CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA
  ```
- Images are tagged with `$CI_COMMIT_SHORT_SHA` (matching the `sha[:8]` lookup in `build_service.py`).

### C. Switching Orchestrator to Real
1. Update `.env`:
   ```ini
   ORCHESTRATOR_MODE=real
   ORCHESTRATOR_URL=http://orchestrator.gandal.local:8080
   ```
2. Confirm the Orchestrator accepts `POST /deployments` and responds with `202 Accepted` + `{"deployment_ref": "..."}`.
3. Confirm the Orchestrator can reach our `$WEBHOOK_PUBLIC_URL/internal/deployments/{id}/status` with `X-Internal-Token`.

### D. Switching Auth to OAuth
1. Update `.env`:
   ```ini
   AUTH_MODE=oauth
   ```
2. Register OAuth application in GitLab. The Developer Portal passes `Authorization: Bearer <gitlab_access_token>`.

---

## 8. Runbook & Troubleshooting

- **Webhook not arriving**:
  - Check firewall between GitLab server and Backend (`$WEBHOOK_PUBLIC_URL`).
  - In GitLab UI: Navigate to Project > Settings > Webhooks > **Recent Deliveries** to inspect response codes and network errors.
  - Verify `WEBHOOK_SECRET` matches in GitLab webhook config and Backend `.env`.
- **Runner offline**:
  - Student pushes code but status remains `awaiting_push` or pipeline stays `pending` indefinitely.
  - Check runner VM: `gitlab-runner status`.
- **Image tag missing (`image tag ... not found in registry`)**:
  - Ensure the CI template tags the image with `$CI_COMMIT_SHORT_SHA` (8 characters).
  - Verify GitLab Container Registry is enabled for the project group and permissions allow reading tags.
- **Orchestrator unreachable**:
  - Check `ORCHESTRATOR_URL` connectivity and DNS resolution.
  - Verify network policies permit egress from Backend to Orchestrator and ingress back to `/internal/*`.
