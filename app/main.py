from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401  (importing registers the tables)
from app.api import files
from app.db import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Geospatial File Measurement API",
    description="Upload a Shapefile (.zip) or KML and get area/length measurements.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(files.router)


@app.get("/health")
def health_check():
    """Simple endpoint to confirm the server is running."""
    return {"status": "ok"}