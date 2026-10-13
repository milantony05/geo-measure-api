"""The /api/files endpoints. Kept thin: real work happens in app/services."""
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app import crud
from app.config import MAX_UPLOAD_BYTES, MAX_UPLOAD_MB
from app.db import get_db
from app.models import Feature, FileStatus, UploadedFile
from app.schemas import FeatureOut, FileInfo, Measurement, MeasurementsResponse
from app.services.errors import GeoFileError, ReprojectionError
from app.services.measure import measure_features
from app.services.reader import read_geofile
from app.services.reproject import make_reprojector
from app.services.export import csv_filename, measurements_to_csv

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


def _to_feature_out(f: Feature, reproject, output_crs: str) -> FeatureOut:
    measurement = None
    if f.measurement_type is not None:
        measurement = Measurement(
            type=f.measurement_type, value=f.measurement_value, unit=f.measurement_unit
        )
    return FeatureOut(
        feature_index=f.feature_index,
        geometry_type=f.geometry_type,
        geometry=reproject(f.geometry),
        crs=output_crs,  # describes the coordinates in `geometry`
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


def _get_completed_file(db: Session, file_id: str) -> UploadedFile:
    record = crud.get_file(db, file_id)
    if record is None:
        raise HTTPException(404, "File not found.")
    if record.status != FileStatus.COMPLETED.value:
        raise HTTPException(409, f"File is not ready (status: {record.status}). {record.error or ''}".strip())
    return record


@router.get("/{file_id}/", response_model=FileInfo)
def get_file_info(file_id: str, db: Session = Depends(get_db)):
    """Return basic information about an uploaded file."""
    record = crud.get_file(db, file_id)
    if record is None:
        raise HTTPException(404, "File not found.")
    return record


@router.get("/{file_id}/measurements/", response_model=MeasurementsResponse)
def get_measurements(
    file_id: str,
    crs: str | None = Query(
        default=None,
        description="Return geometries in this CRS, e.g. EPSG:4326. "
        "Default: the file's original CRS. Measurements are not affected.",
    ),
    db: Session = Depends(get_db),
):
    """Return every feature in the file with its measurement."""
    record = _get_completed_file(db, file_id)

    if crs is None:
        reproject, output_crs = (lambda geometry: geometry), record.crs
    else:
        try:
            reproject, output_crs = make_reprojector(record.crs, crs)
        except ReprojectionError as exc:
            raise HTTPException(400, str(exc))

    return MeasurementsResponse(
        id=record.id,
        filename=record.filename,
        crs=record.crs,
        projected_crs=record.projected_crs,
        feature_count=record.feature_count,
        features=[_to_feature_out(f, reproject, output_crs) for f in record.features],
    )


@router.get("/{file_id}/measurements.csv", response_class=Response)
def export_measurements_csv(file_id: str, db: Session = Depends(get_db)):
    """Download the measurements as a CSV file."""
    record = _get_completed_file(db, file_id)
    # "utf-8-sig" adds a byte-order mark so Excel detects UTF-8 and shows non-English names correctly.
    content = measurements_to_csv(record.features).encode("utf-8-sig")
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{csv_filename(record.filename)}"'},
    )