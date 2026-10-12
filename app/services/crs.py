"""Choosing a projected CRS (units in metres) for accurate measurements."""
import geopandas as gpd
from pyproj import CRS

from app.services.errors import GeoFileError


def crs_label(crs: CRS) -> str:
    """Human-friendly CRS name, e.g. 'EPSG:4326'."""
    authority = crs.to_authority()  # e.g. ('EPSG', '4326'), or None
    return f"{authority[0]}:{authority[1]}" if authority else crs.name


def pick_projected_crs(gdf: gpd.GeoDataFrame) -> CRS:
    """Pick the best-fitting UTM zone for the data.

    UTM splits the world into 60 north-south zones, each 6 degrees wide, and
    gives coordinates in metres. geopandas looks at where the data is and
    chooses the matching zone (e.g. EPSG:32643 for Bengaluru).
    """
    if gdf.geometry.isna().all() or gdf.geometry.is_empty.all():
        raise GeoFileError("The file has no usable geometries.")
    return gdf.estimate_utm_crs()