from fastapi import FastAPI

app = FastAPI(
    title="Geospatial File Measurement API",
    description="Upload a Shapefile (.zip) or KML and get area/length measurements.",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    """Simple endpoint to confirm the server is running."""
    return {"status": "ok"}