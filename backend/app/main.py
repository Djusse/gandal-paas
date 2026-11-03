import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.deps import get_orchestrator
from app.routers import health, internal, projects, webhooks
from app.services.deployment_service import DeploymentRecovery

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("backend")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Une instance par cycle de vie : la tâche asynchrone et son événement
    # d'arrêt appartiennent à la boucle qui les utilise (R1, R11).
    recovery = DeploymentRecovery(get_orchestrator)
    app.state.recovery = recovery
    recovery.start()
    try:
        yield
    finally:
        await recovery.stop()


app = FastAPI(
    title="GANDAL PaaS API",
    description="Backend service for GANDAL PaaS - bridges Developer Portal, GitLab, CI Registry and Kubernetes Orchestrator",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=settings.cors_origin_list != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(projects.router)
app.include_router(webhooks.router)
app.include_router(internal.router)


@app.get("/")
def root():
    return {
        "service": "GANDAL PaaS Backend",
        "version": "1.1.0",
        "docs_url": "/docs"
    }
