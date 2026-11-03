from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models import Project, PipelineEvent, Image, Deployment
from app.services.deployment_service import send_deployment


def check_name_available(db: Session, name: str) -> None:
    """Unicité globale des noms de projet (contrainte produit, §2.1 du plan)."""
    existing = db.query(Project).filter_by(name=name).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Project with name '{name}' already exists")


async def create_project(db: Session, gl, name: str, owner: str, app_port: int) -> Project:
    check_name_available(db, name)

    p = Project(
        name=name,
        owner=owner,
        k8s_namespace=f'proj-{name}',
        app_port=app_port,
        status='creating'
    )
    db.add(p)
    db.commit()
    db.refresh(p)

    gid = None
    try:
        g = await gl.create_project(name)
        gid = g['id']
        await gl.create_webhook(gid)
        p.gitlab_project_id, p.repo_url = gid, g['web_url']
        p.status = 'awaiting_push'
        db.commit()
        db.refresh(p)
    except Exception as e:
        if gid:
            try:
                await gl.delete_project(gid)
            except Exception:
                pass
        p.status, p.error = 'failed', str(e)[:500]
        db.commit()
        raise
    return p


def get_user_project(db: Session, project_id: int, owner: str) -> Project:
    p = db.get(Project, project_id)
    if not p or p.owner != owner:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


def list_user_projects(db: Session, owner: str) -> list[Project]:
    return db.query(Project).filter_by(owner=owner).order_by(Project.id.desc()).all()


def get_project_events(db: Session, project_id: int, owner: str) -> list[PipelineEvent]:
    get_user_project(db, project_id, owner)
    return db.query(PipelineEvent).filter_by(project_id=project_id).order_by(PipelineEvent.received_at.desc()).all()


def get_project_images(db: Session, project_id: int, owner: str) -> list[Image]:
    get_user_project(db, project_id, owner)
    return db.query(Image).filter_by(project_id=project_id).order_by(Image.pushed_at.desc()).all()


async def manual_deploy(db: Session, orch, project_id: int, owner: str, image_id: int | None = None) -> Deployment:
    p = get_user_project(db, project_id, owner)
    if image_id:
        img = db.get(Image, image_id)
        if not img or img.project_id != p.id:
            raise HTTPException(status_code=404, detail="Image not found for this project")
    else:
        img = db.query(Image).filter_by(project_id=p.id).order_by(Image.id.desc()).first()
        if not img:
            raise HTTPException(status_code=400, detail="No built image available for deployment")

    dep = Deployment(project_id=p.id, image_id=img.id, status='requested')
    db.add(dep)
    db.commit()
    db.refresh(dep)

    p.status = 'deploying'
    p.error = None
    db.commit()

    try:
        # Même chemin que le webhook : commit déjà fait, appel idempotent (R1).
        await send_deployment(db, orch, p, dep, img)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Orchestrator error: {e}")

    db.refresh(dep)
    return dep


async def delete_project(db: Session, orch, project_id: int, owner: str) -> None:
    """Supprime un projet : namespace (si l'orchestrateur le permet) et lignes."""
    p = get_user_project(db, project_id, owner)

    if orch is not None and hasattr(orch, "delete_project"):
        try:
            await orch.delete_project(p.k8s_namespace)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Orchestrator error: {e}") from e

    db.query(Deployment).filter_by(project_id=p.id).delete()
    db.query(Image).filter_by(project_id=p.id).delete()
    db.query(PipelineEvent).filter_by(project_id=p.id).delete()
    db.delete(p)
    db.commit()
