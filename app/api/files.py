"""The /api/files endpoints. Kept thin: real work happens in app/services."""
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import crud
from app.config import MAX_UPLOAD_BYTES, MAX_UPLOAD_MB
from app.db import get_db
from app.models import Feature, FileStatus
from app.schemas import FeatureOut, FileInfo, Measurement, MeasurementsResponse
from app.services.errors import GeoFileError
from app.services.measure import measure_features
from app.services.reader import read_geofile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])

ALLOWED_SUFFIXES = {".kml", ".zip"}
CHUNK_SIZE = 1024 * 1024  # read uploads 1 MB at a time


def _save_upload(upload: UploadFile, dest: Path) -> None:
    """Copy the upload to disk in chunks, enforcing the size limit."""
    written = 0
    with dest.open("wb") as out:
        while chunk := upload.file.read(CHUNK_SIZE):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                raise HTTPException(413, f"File is too large (limit is {MAX_UPLOAD_MB} MB).")
            out.write(chunk)
    if written == 0:
        raise HTTPException(400, "Uploaded file is empty.")


def _to_feature_out(f: Feature) -> FeatureOut:
    measurement = None
    if f.measurement_type is not None:
        measurement = Measurement(
            type=f.measurement_type, value=f.measurement_value, unit=f.measurement_unit
        )
    return FeatureOut(
        feature_index=f.feature_index,
        geometry_type=f.geometry_type,
        geometry=f.geometry,
        crs=f.crs,
        properties=f.properties,
        measurement=measurement,
        note=f.note,
    )


@router.post("/", response_model=FileInfo, status_code=201)
def upload_file(file: UploadFile, db: Session = Depends(get_db)):
    """Upload a .kml or a .zip (Shapefile), process it, and store the results."""
    original_name = Path(file.filename or "").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(400, "Unsupported file type. Upload a .kml or a .zip containing a Shapefile.")

    # Save to a throwaway folder. We never use the user's filename as a path.
    with tempfile.TemporaryDirectory() as tmp:
        saved_path = Path(tmp) / f"upload{suffix}"
        _save_upload(file, saved_path)

        record = crud.create_file(db, original_name)  # status = PROCESSING
        try:
            gdf = read_geofile(saved_path)
            result = measure_features(gdf)
            record = crud.save_result(db, record, result)  # status = COMPLETED
        except GeoFileError as exc:
            db.rollback()
            crud.mark_failed(db, record, str(exc))
            raise HTTPException(
                422, detail={"file_id": record.id, "status": "FAILED", "message": str(exc)}
            )
        except Exception:
            logger.exception("Unexpected error while processing %s", original_name)
            db.rollback()
            crud.mark_failed(db, record, "Unexpected error while processing the file.")
            raise HTTPException(
                500,
                detail={"file_id": record.id, "status": "FAILED",
                        "message": "Unexpected error while processing the file."},
            )

    return record


@router.get("/{file_id}/", response_model=FileInfo)
def get_file_info(file_id: str, db: Session = Depends(get_db)):
    """Return basic information about an uploaded file."""
    record = crud.get_file(db, file_id)
    if record is None:
        raise HTTPException(404, "File not found.")
    return record


@router.get("/{file_id}/measurements/", response_model=MeasurementsResponse)
def get_measurements(file_id: str, db: Session = Depends(get_db)):
    """Return every feature in the file with its measurement."""
    record = crud.get_file(db, file_id)
    if record is None:
        raise HTTPException(404, "File not found.")
    if record.status != FileStatus.COMPLETED.value:
        raise HTTPException(409, f"File is not ready (status: {record.status}). {record.error or ''}".strip())

    return MeasurementsResponse(
        id=record.id,
        filename=record.filename,
        crs=record.crs,
        projected_crs=record.projected_crs,
        feature_count=record.feature_count,
        features=[_to_feature_out(f) for f in record.features],
    )