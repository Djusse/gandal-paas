from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class ProjectCreate(BaseModel):
    name: str = Field(pattern=r'^[a-z][a-z0-9-]{2,29}$', description="Project slug (lowercase, 3-30 chars, starts with letter)")
    app_port: int = Field(default=8080, ge=1, le=65535, description="Port the app listens on in container")


class ProjectRead(BaseModel):
    id: int
    name: str
    owner: str
    gitlab_project_id: int | None = None
    repo_url: str | None = None
    k8s_namespace: str
    app_port: int
    status: str
    error: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PipelineEventRead(BaseModel):
    id: int
    project_id: int
    pipeline_id: int
    sha: str
    status: str
    received_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ImageRead(BaseModel):
    id: int
    project_id: int
    repository: str
    tag: str
    digest: str | None = None
    pushed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DeploymentRead(BaseModel):
    id: int
    project_id: int
    image_id: int
    status: str
    orchestrator_ref: str | None = None
    url: str | None = None
    message: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DeploymentStatusCallback(BaseModel):
    status: str = Field(pattern=r'^(deploying|deployed|failed)$')
    url: str | None = None
    message: str | None = None


class ManualDeployRequest(BaseModel):
    image_id: int | None = Field(default=None, description="Optional specific image ID to deploy. Defaults to latest image.")
