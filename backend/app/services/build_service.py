import logging

from app.db import SessionLocal
from app.deps import get_gitlab, get_orchestrator
from app.models import Deployment, Image, Project
from app.services.deployment_service import send_deployment

log = logging.getLogger("build-service")


async def on_build_success(project_id: int, sha: str):
    db = SessionLocal()
    try:
        p = db.get(Project, project_id)
        if not p:
            log.warning("Project id %s not found in on_build_success", project_id)
            return

        wanted = sha[:8]    # matches CI_COMMIT_SHORT_SHA used by the template
        tags = await get_gitlab().list_images(p.gitlab_project_id, sha)
        t = next((x for x in tags if x['tag'] == wanted), None)
        if not t:
            p.status, p.error = 'failed', f'image tag {wanted} not found in registry'
            db.commit()
            return

        img = Image(project_id=p.id, repository=t['repository'], tag=t['tag'], digest=t.get('digest'))
        dep = Deployment(project_id=p.id, image_id=0, status='requested')
        db.add(img)
        db.flush()
        dep.image_id = img.id
        db.add(dep)

        # R1 : on commite AVANT l'appel à l'orchestrateur. La ligne est ainsi
        # visible du callback, et un commit tardif ne peut plus écraser un
        # statut `deployed` par `deploying`.
        p.status = 'deploying'
        p.error = None
        db.commit()
        db.refresh(dep)

        await send_deployment(db, get_orchestrator(), p, dep, img)
    except Exception as e:
        log.exception("Error handling build success for project %s: %s", project_id, e)
        db.rollback()
        p = db.get(Project, project_id)
        if p:
            p.status, p.error = 'failed', str(e)[:500]
            db.commit()
    finally:
        db.close()
