"""Tests d'intégration sur PostgreSQL (correction R1).

Contrairement aux tests unitaires (SQLite en mémoire, une seule connexion), ce
module vérifie la **visibilité inter-transactions** : la ligne ``Deployment``
doit être commitée avant que l'orchestrateur soit appelé, sinon un callback
rapide renverrait 404 ou verrait son statut écrasé.

Lancer avec un PostgreSQL réel :

    PG_TEST_URL=postgresql+psycopg://paas:paas@localhost:5432/paas_test pytest -q tests_integration
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

PG_URL = os.getenv("PG_TEST_URL")

pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="PG_TEST_URL non défini : test PostgreSQL ignoré (utiliser deploy/test-postgres.sh)",
)


@pytest.fixture(scope="module")
def engine():
    from app.models import Base

    engine = create_engine(PG_URL, pool_pre_ping=True)
    # Base.cache_clear() évite de réutiliser un introspecteur SQLite.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session_factory(engine):
    from app.models import Base

    # Chaque test part d'une base vide : les noms de projet sont uniques.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def seeded(session_factory):
    from app.models import Image, Project

    session = session_factory()
    project = Project(
        name="race-pg-app",
        owner="alice",
        k8s_namespace="proj-race-pg-app",
        app_port=8080,
        status="deploying",
    )
    session.add(project)
    session.commit()
    image = Image(
        project_id=project.id,
        repository="localhost:5000/paas/race-pg-app",
        tag="a1b2c3d4",
        digest="sha256:" + "0" * 64,
    )
    session.add(image)
    session.commit()
    project_id, image_id = project.id, image.id
    session.close()
    return project_id, image_id


def test_database_is_postgresql(engine):
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar()
    assert "PostgreSQL" in version


def test_row_visible_from_another_connection_after_commit(session_factory, seeded):
    """R1 : la ligne commitée est immédiatement visible d'une autre session."""
    from app.models import Deployment

    project_id, image_id = seeded

    writer = session_factory()
    deployment = Deployment(project_id=project_id, image_id=image_id, status="requested")
    writer.add(deployment)
    writer.commit()
    deployment_id = deployment.id
    writer.close()

    reader = session_factory()
    try:
        seen = reader.execute(
            text("SELECT status FROM deployments WHERE id = :id"), {"id": deployment_id}
        ).scalar()
    finally:
        reader.close()

    assert seen == "requested"


def test_uncommitted_row_is_invisible(session_factory, seeded):
    """Contre-preuve : sans commit, le callback recevrait un 404 (le défaut R1)."""
    from app.models import Deployment

    project_id, image_id = seeded
    writer = session_factory()
    deployment = Deployment(project_id=project_id, image_id=image_id, status="requested")
    writer.add(deployment)
    writer.flush()          # comme l'ancien build_service : flush, pas commit
    deployment_id = deployment.id

    reader = session_factory()
    try:
        count = reader.execute(
            text("SELECT count(*) FROM deployments WHERE id = :id"), {"id": deployment_id}
        ).scalar()
    finally:
        reader.close()
        writer.rollback()
        writer.close()

    assert count == 0


def test_callback_does_not_overwrite_deployed(session_factory, seeded):
    """Le commit tardif ne doit pas faire repasser un déploiement `deployed` à `deploying`."""
    from app.models import Deployment
    from app.services.deployment_service import is_monotonic

    project_id, image_id = seeded

    session = session_factory()
    deployment = Deployment(project_id=project_id, image_id=image_id, status="requested")
    session.add(deployment)
    session.commit()
    deployment.status = "deployed"
    session.commit()
    deployment_id = deployment.id
    session.close()

    # Arrive un `deploying` tardif : refusé par la règle de monotonie.
    assert is_monotonic("deployed", "deploying") is False

    check = session_factory()
    try:
        status = check.execute(
            text("SELECT status FROM deployments WHERE id = :id"), {"id": deployment_id}
        ).scalar()
    finally:
        check.close()

    assert status == "deployed"


def test_duplicate_project_name_rejected_by_database(session_factory, seeded):
    """L'unicité globale du nom est garantie par la base, pas seulement par le service."""
    from sqlalchemy.exc import IntegrityError

    from app.models import Project

    session = session_factory()
    session.add(
        Project(name="race-pg-app", owner="bob", k8s_namespace="proj-race-pg-app", app_port=8080)
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.close()
