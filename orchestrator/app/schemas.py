"""Schémas d'entrée et de sortie du service HTTP de l'orchestrateur."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DeploymentRequest(BaseModel):
    """Corps de ``POST /deployments`` (contrat partagé avec le backend)."""

    deployment_id: int = Field(gt=0)
    project: str = Field(min_length=1, max_length=63)
    owner: str = Field(default="", max_length=100)
    namespace: str = Field(min_length=1, max_length=63)
    image: str = Field(min_length=1)
    tag: str | None = None
    digest: str | None = None
    port: int = Field(ge=1, le=65535)
    replicas: int | None = Field(default=None, ge=1, le=10)


class DeploymentAccepted(BaseModel):
    deployment_ref: str
    status: str = "deploying"
    url: str | None = None
    message: str = ""


class DeploymentState(BaseModel):
    deployment_ref: str
    status: str
    url: str | None = None
    message: str = ""


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    kubernetes: bool
    reconciler: bool
