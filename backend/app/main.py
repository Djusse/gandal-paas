from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import health, projects, webhooks, internal

app = FastAPI(
    title="GANDAL PaaS API",
    description="Backend service for GANDAL PaaS - bridges Developer Portal, GitLab, CI Registry and Kubernetes Orchestrator",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
        "version": "1.0.0",
        "docs_url": "/docs"
    }
