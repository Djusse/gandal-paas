import hmac
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import Deployment, Project
from app.schemas import DeploymentStatusCallback

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/deployments/{deployment_id}/status")
def update_deployment_status(
    deployment_id: int,
    payload: DeploymentStatusCallback,
    db: Session = Depends(get_db),
    x_internal_token: str = Header(default="", alias="X-Internal-Token"),
):
    if not hmac.compare_digest(x_internal_token, settings.internal_token):
        raise HTTPException(status_code=401, detail="Invalid internal token")

    deployment = db.get(Deployment, deployment_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    deployment.status = payload.status
    if payload.url:
        deployment.url = payload.url
    if payload.message:
        deployment.message = payload.message

    project = db.get(Project, deployment.project_id)
    if project:
        if payload.status == "deployed":
            project.status = "deployed"
            project.error = None
        elif payload.status == "failed":
            project.status = "failed"
            project.error = payload.message or "Deployment failed"
        elif payload.status == "deploying":
            project.status = "deploying"

    db.commit()
    return {"ok": True}
