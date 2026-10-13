"""Reprojecting GeoJSON geometries between coordinate systems (for display)."""
from collections.abc import Callable

from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError
from shapely.geometry import mapping, shape
from shapely.ops import transform

from app.services.crs import crs_label
from app.services.errors import ReprojectionError

GeoJSONGeometry = dict | None


def make_reprojector(
    source_crs: str, target_crs: str
) -> tuple[Callable[[GeoJSONGeometry], GeoJSONGeometry], str]:
    """Return (function that reprojects one GeoJSON geometry, label of the target CRS)."""
    try:
        source = CRS.from_user_input(source_crs)
        target = CRS.from_user_input(target_crs)
    except CRSError as exc:
        raise ReprojectionError(f"Unknown or unsupported CRS: {exc}") from exc

    label = crs_label(target)

    if source == target:
        return (lambda geometry: geometry), label

    # always_xy=True keeps the order (x, y) = (longitude, latitude) / (easting, northing).
    # Without it, pyproj would follow EPSG:4326's official lat/lon order and swap them.
    transformer = Transformer.from_crs(source, target, always_xy=True)

    def reproject(geometry: GeoJSONGeometry) -> GeoJSONGeometry:
        if geometry is None:
            return None
        return mapping(transform(transformer.transform, shape(geometry)))

    return reproject, label