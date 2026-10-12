"""Pydantic models describing the API's JSON responses."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # lets us build it from a DB object

    id: str
    filename: str
    feature_count: int
    crs: str | None
    status: str
    error: str | None = None
    created_at: datetime


class Measurement(BaseModel):
    type: str      # "area" or "length"
    value: float
    unit: str      # "m2" or "m"


class FeatureOut(BaseModel):
    feature_index: int
    geometry_type: str | None
    geometry: dict | None
    crs: str
    properties: dict
    measurement: Measurement | None
    note: str | None


class MeasurementsResponse(BaseModel):
    id: str
    filename: str
    crs: str | None
    projected_crs: str | None
    feature_count: int
    features: list[FeatureOut]