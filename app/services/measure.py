"""Per-feature extraction and measurement."""
import json
from dataclasses import dataclass

import geopandas as gpd

from app.services.crs import crs_label, pick_projected_crs

AREA_TYPES = {"Polygon", "MultiPolygon"}
LENGTH_TYPES = {"LineString", "MultiLineString", "LinearRing"}
NO_MEASUREMENT_TYPES = {"Point", "MultiPoint"}  # nothing to measure, and that's fine


@dataclass
class MeasurementResult:
    source_crs: str
    projected_crs: str
    features: list[dict]


def measure_features(gdf: gpd.GeoDataFrame) -> MeasurementResult:
    """Return info + measurements for every feature in the GeoDataFrame."""
    projected_crs = pick_projected_crs(gdf)
    projected = gdf.to_crs(projected_crs)  # same features, now in metres

    # to_json() gives us JSON-safe geometry and properties
    # (it converts NaN -> null, dates -> strings, numpy types -> plain numbers).
    geojson_features = json.loads(gdf.to_json(drop_id=True))["features"]
    source_crs = crs_label(gdf.crs)

    features = [
        _measure_one(index, feature, proj_geom, source_crs)
        for index, (feature, proj_geom) in enumerate(zip(geojson_features, projected.geometry))
    ]
    return MeasurementResult(
        source_crs=source_crs,
        projected_crs=crs_label(projected_crs),
        features=features,
    )


def _measure_one(index: int, feature: dict, proj_geom, source_crs: str) -> dict:
    measurement = None
    note = None

    if proj_geom is None or proj_geom.is_empty:
        geom_type = None
        note = "Feature has no geometry."
    else:
        geom_type = proj_geom.geom_type
        if geom_type in AREA_TYPES:
            measurement = {"type": "area", "value": round(proj_geom.area, 3), "unit": "m2"}
        elif geom_type in LENGTH_TYPES:
            measurement = {"type": "length", "value": round(proj_geom.length, 3), "unit": "m"}
        elif geom_type not in NO_MEASUREMENT_TYPES:
            note = f"Measurement is not supported for geometry type '{geom_type}'."

        if not proj_geom.is_valid:
            note = ((note + " ") if note else "") + "Geometry is invalid; measurement may be inaccurate."

    return {
        "feature_index": index,
        "geometry_type": geom_type,
        "geometry": feature["geometry"],  # GeoJSON, in the file's ORIGINAL CRS
        "crs": source_crs,
        "properties": feature["properties"],
        "measurement": measurement,
        "note": note,
    }