import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.main import app
from app.db import get_db
from app.models import Base
from app import deps
import app.services.build_service as bs
import app.services.deployment_service as ds

TEST_DB_URL = "sqlite:///:memory:"

engine_test = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine_test, expire_on_commit=False)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine_test)
    Base.metadata.create_all(bind=engine_test)
    # Reset fake adapters state
    deps._gl_fake.projects.clear()
    deps._gl_fake._next = 1
    deps._gl_fake.fail_create = False
    deps._gl_fake.custom_images.clear()
    deps._orch_mock.callback_delay = 0.0
    deps._orch_mock.deployments.clear()
    yield
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture(autouse=True)
def isolate_services(monkeypatch):
    """Tâches de fond désactivées et sessions de service sur la base de test."""
    monkeypatch.setattr(settings, "recovery_enabled", False)
    monkeypatch.setattr(bs, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(ds, "SessionLocal", TestingSessionLocal)


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def session_factory():
    """Fabrique de sessions indépendantes (relance, appels inter-sessions)."""
    return TestingSessionLocal


@pytest.fixture
def client(monkeypatch):
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(bs, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(ds, "SessionLocal", TestingSessionLocal)

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
