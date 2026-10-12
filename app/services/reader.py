"""Reading geospatial files (KML or zipped Shapefile) into a GeoDataFrame."""
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd

from app.services.errors import GeoFileError

MAX_UNZIPPED_BYTES = 200 * 1024 * 1024  # 200 MB safety limit


def read_geofile(path: Path) -> gpd.GeoDataFrame:
    """Read a .kml or .zip (containing a Shapefile) and return a GeoDataFrame."""
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".kml":
        gdf = _read_kml(path)
    elif suffix == ".zip":
        gdf = _read_zipped_shapefile(path)
    else:
        raise GeoFileError(
            f"Unsupported file type '{suffix}'. Upload a .kml or a .zip containing a Shapefile."
        )

    return _validate(gdf)


def _read_kml(path: Path) -> gpd.GeoDataFrame:
    try:
        return gpd.read_file(path)
    except Exception as exc:
        raise GeoFileError(f"Could not read KML file: {exc}") from exc


def _read_zipped_shapefile(path: Path) -> gpd.GeoDataFrame:
    # TemporaryDirectory is deleted automatically when the `with` block ends.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        try:
            with zipfile.ZipFile(path) as zf:
                _safe_extract(zf, tmp_dir)
        except zipfile.BadZipFile as exc:
            raise GeoFileError("File is not a valid zip archive.") from exc

        # Ignore junk that macOS adds to zips (__MACOSX folder, ._files)
        shp_files = sorted(
            p
            for p in tmp_dir.rglob("*.shp")
            if "__MACOSX" not in p.parts and not p.name.startswith("._")
        )
        if not shp_files:
            raise GeoFileError("The zip archive does not contain a .shp file.")

        try:
            return gpd.read_file(shp_files[0])
        except Exception as exc:
            raise GeoFileError(f"Could not read Shapefile: {exc}") from exc


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    """Extract a zip, refusing zip bombs and 'zip slip' attacks."""
    total_size = sum(info.file_size for info in zf.infolist())
    if total_size > MAX_UNZIPPED_BYTES:
        raise GeoFileError("Zip archive is too large once extracted.")

    dest_resolved = dest.resolve()
    for info in zf.infolist():
        # A malicious zip can contain names like "../../evil.py".
        target = (dest / info.filename).resolve()
        if not target.is_relative_to(dest_resolved):
            raise GeoFileError("Zip archive contains an unsafe file path.")

    zf.extractall(dest)


def _validate(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        raise GeoFileError(
            "The file has no coordinate reference system (CRS). "
            "For Shapefiles, make sure the .prj file is included in the zip."
        )
    if len(gdf) == 0:
        raise GeoFileError("The file contains no features.")

    # KML often has a Z (altitude) value. Area/length are 2D, so drop Z.
    return gdf.set_geometry(gdf.geometry.force_2d())