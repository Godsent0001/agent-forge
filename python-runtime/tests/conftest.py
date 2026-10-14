import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.deps import get_db
from main import app


@pytest.fixture(autouse=True)
def use_fake_runner_for_tests(monkeypatch):
    # Unit/API tests must be deterministic and must never call paid providers.
    # Individual runner-factory tests can explicitly unset/override this value.
    monkeypatch.setenv("AGENTFORGE_RUNNER", "fake")


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)

@pytest.fixture()
def client(db_session, monkeypatch):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setenv("AGENTFORGE_TOKEN", "test-token")
    monkeypatch.delenv("AGENTFORGE_DEV", raising=False)
    try:
        yield TestClient(app, headers={"Authorization": "Bearer test-token"})
    finally:
        app.dependency_overrides.clear()
