import logging
from app.db import SessionLocal
from app.deps import get_gitlab, get_orchestrator
from app.models import Project, Image, Deployment

log = logging.getLogger("build-service")


async def on_build_success(project_id: int, sha: str):
    db = SessionLocal()
    try:
        p = db.get(Project, project_id)
        if not p:
            log.warning("Project id %s not found in on_build_success", project_id)
            return

        tags = await get_gitlab().list_images(p.gitlab_project_id)
        wanted = sha[:8]    # matches CI_COMMIT_SHORT_SHA used by the template
        t = next((x for x in tags if x['tag'] == wanted), None)
        if not t:
            p.status, p.error = 'failed', f'image tag {wanted} not found in registry'
            db.commit()
            return

        img = Image(project_id=p.id, repository=t['repository'], tag=t['tag'], digest=t.get('digest'))
        dep = Deployment(project_id=p.id, image_id=0)
        db.add(img)
        db.flush()
        dep.image_id = img.id
        db.add(dep)
        db.flush()

        res = await get_orchestrator().deploy({
            'deployment_id': dep.id,
            'project': p.name,
            'namespace': p.k8s_namespace,
            'image': img.repository,
            'tag': img.tag,
            'digest': img.digest,
            'port': p.app_port,
            'replicas': 1
        })
        dep.orchestrator_ref, dep.status, p.status = res['deployment_ref'], 'requested', 'deploying'
        db.commit()
    except Exception as e:
        log.exception("Error handling build success for project %s: %s", project_id, e)
        db.rollback()
        p = db.get(Project, project_id)
        if p:
            p.status, p.error = 'failed', str(e)[:500]
            db.commit()
    finally:
        db.close()
