from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.db import get_db
from app.deps import get_current_user, get_gitlab, get_orchestrator
from app.schemas import (
    ProjectCreate,
    ProjectRead,
    PipelineEventRead,
    ImageRead,
    DeploymentRead,
    ManualDeployRequest,
    DeleteResult,
)
from app.services import project_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    gl=Depends(get_gitlab),
    current_user: str = Depends(get_current_user),
):
    project = await project_service.create_project(
        db=db,
        gl=gl,
        name=payload.name,
        owner=current_user,
        app_port=payload.app_port
    )
    return project


@router.get("", response_model=list[ProjectRead])
def list_projects(
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    return project_service.list_user_projects(db, current_user)


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    return project_service.get_user_project(db, project_id, current_user)


@router.delete("/{project_id}", response_model=DeleteResult)
async def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    orch=Depends(get_orchestrator),
    current_user: str = Depends(get_current_user),
):
    """Suppression complète : namespace Kubernetes (si géré) et lignes associées."""
    await project_service.delete_project(db, orch, project_id, current_user)
    return DeleteResult(deleted=True, message=f"Project {project_id} deleted")


@router.get("/{project_id}/builds", response_model=list[PipelineEventRead])
def get_project_builds(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    return project_service.get_project_events(db, project_id, current_user)


@router.get("/{project_id}/images", response_model=list[ImageRead])
def get_project_images(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    return project_service.get_project_images(db, project_id, current_user)


@router.post("/{project_id}/deploy", response_model=DeploymentRead)
async def deploy_project(
    project_id: int,
    payload: ManualDeployRequest | None = None,
    db: Session = Depends(get_db),
    orch=Depends(get_orchestrator),
    current_user: str = Depends(get_current_user),
):
    image_id = payload.image_id if payload else None
    return await project_service.manual_deploy(
        db=db,
        orch=orch,
        project_id=project_id,
        owner=current_user,
        image_id=image_id
    )


@router.get("/{project_id}/deployments", response_model=list[DeploymentRead])
def list_deployments(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Historique des déploiements d'un projet (utile au diagnostic R1)."""
    from app.models import Deployment

    project_service.get_user_project(db, project_id, current_user)
    return (
        db.query(Deployment)
        .filter_by(project_id=project_id)
        .order_by(Deployment.id.desc())
        .all()
    )
