"""Database session factory and schema initialization."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from newgrad_notifier.config.settings import AppSettings
from newgrad_notifier.db.models import Base


def create_sqlalchemy_engine(settings: AppSettings):
    """Create an engine from configured database settings."""

    database_url = settings.database.url
    if database_url.startswith("postgres://"):
        database_url = "postgresql+psycopg://" + database_url.removeprefix("postgres://")
    elif database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    if database_url.startswith("sqlite:///"):
        db_file = database_url.removeprefix("sqlite:///")
        if db_file.startswith("./"):
            Path(db_file).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url, echo=settings.database.echo, future=True)


def create_session_factory(settings: AppSettings) -> sessionmaker[Session]:
    """Create a configured SQLAlchemy sessionmaker."""

    engine = create_sqlalchemy_engine(settings)
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


def init_db(settings: AppSettings) -> None:
    """Create all database tables."""

    engine = create_sqlalchemy_engine(settings)
    Base.metadata.create_all(engine)
