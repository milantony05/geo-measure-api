"""Database connection setup."""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Can be overridden with an environment variable (useful later for Docker).
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./geo.db")

# check_same_thread=False is needed for SQLite because FastAPI may use
# different threads for the same request lifecycle.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """All table classes inherit from this."""


def get_db():
    """FastAPI dependency: gives each request its own session, then closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()