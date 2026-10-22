from datetime import datetime
from sqlalchemy import String, DateTime, JSON, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Project(Base):
    __tablename__ = 'projects'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(31), unique=True, index=True)
    owner: Mapped[str] = mapped_column(String(100), index=True)
    gitlab_project_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    repo_url: Mapped[str | None] = mapped_column(nullable=True)
    k8s_namespace: Mapped[str] = mapped_column(String(63))
    app_port: Mapped[int] = mapped_column(default=8080)
    status: Mapped[str] = mapped_column(String(30), default='creating')
    error: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class PipelineEvent(Base):
    __tablename__ = 'pipeline_events'
    __table_args__ = (UniqueConstraint('pipeline_id', 'status', name='uq_pipeline_event_id_status'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id'), index=True)
    pipeline_id: Mapped[int] = mapped_column(index=True)
    sha: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class Image(Base):
    __tablename__ = 'images'
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id'), index=True)
    repository: Mapped[str] = mapped_column(String(255))
    tag: Mapped[str] = mapped_column(String(100), index=True)
    digest: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pushed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class Deployment(Base):
    __tablename__ = 'deployments'
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id'), index=True)
    image_id: Mapped[int] = mapped_column(ForeignKey('images.id'), index=True)
    status: Mapped[str] = mapped_column(String(30), default='requested')
    orchestrator_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
