import hmac
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import Project, PipelineEvent
from app.services.build_service import on_build_success

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

STATUS_MAP = {
    'pending': 'building',
    'running': 'building',
    'failed': 'build_failed',
    'canceled': 'build_failed',
    'success': 'built'
}


@router.post('/gitlab')
async def gitlab_webhook(
    request: Request,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    x_gitlab_token: str = Header(default='', alias='X-Gitlab-Token')
):
    if not hmac.compare_digest(x_gitlab_token, settings.webhook_secret):
        raise HTTPException(status_code=401, detail='bad token')

    body = await request.json()
    if body.get('object_kind') != 'pipeline':
        return {'ignored': True}

    attrs = body.get('object_attributes')
    project_info = body.get('project')
    if not attrs or not project_info:
        return {'ignored': True}

    gitlab_project_id = project_info.get('id')
    pipeline_id = attrs.get('id')
    pipeline_status = attrs.get('status')
    sha = attrs.get('sha', '')

    p = db.query(Project).filter_by(gitlab_project_id=gitlab_project_id).order_by(Project.id.desc()).first()
    if not p or pipeline_status not in STATUS_MAP:
        return {'ignored': True}

    # Deduplication: idempotent processing
    existing = db.query(PipelineEvent).filter_by(pipeline_id=pipeline_id, status=pipeline_status).first()
    if existing:
        return {'duplicate': True}

    db.add(PipelineEvent(
        project_id=p.id,
        pipeline_id=pipeline_id,
        sha=sha,
        status=pipeline_status,
        payload=body
    ))
    p.status = STATUS_MAP[pipeline_status]
    db.commit()

    if pipeline_status == 'success':
        bg.add_task(on_build_success, p.id, sha)

    return {'ok': True}
