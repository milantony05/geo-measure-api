"""Database operations."""
from sqlalchemy.orm import Session

from app.models import Feature, FileStatus, UploadedFile
from app.services.measure import MeasurementResult


def create_file(db: Session, filename: str) -> UploadedFile:
    """Insert a new file row with status PROCESSING."""
    file = UploadedFile(filename=filename)
    db.add(file)
    db.commit()
    db.refresh(file)
    return file


def save_result(db: Session, file: UploadedFile, result: MeasurementResult) -> UploadedFile:
    """Store all features and mark the file COMPLETED, in ONE commit."""
    file.crs = result.source_crs
    file.projected_crs = result.projected_crs
    file.feature_count = len(result.features)
    file.status = FileStatus.COMPLETED.value

    for f in result.features:
        m = f["measurement"] or {}
        file.features.append(
            Feature(
                feature_index=f["feature_index"],
                geometry_type=f["geometry_type"],
                geometry=f["geometry"],
                crs=f["crs"],
                properties=f["properties"],
                measurement_type=m.get("type"),
                measurement_value=m.get("value"),
                measurement_unit=m.get("unit"),
                note=f["note"],
            )
        )
    db.commit()
    return file


def mark_failed(db: Session, file: UploadedFile, message: str) -> UploadedFile:
    file.status = FileStatus.FAILED.value
    file.error = message
    db.commit()
    return file


def get_file(db: Session, file_id: str) -> UploadedFile | None:
    return db.get(UploadedFile, file_id)