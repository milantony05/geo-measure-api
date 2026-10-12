"""Reading geospatial files (KML or zipped Shapefile) into a GeoDataFrame."""
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pyogrio import list_layers

from app.services.errors import GeoFileError

MAX_UNZIPPED_BYTES = 200 * 1024 * 1024  # 200 MB safety limit
LAYER_COLUMN = "source_layer"
NO_CRS_MESSAGE = (
    "The file has no coordinate reference system (CRS). "
    "For Shapefiles, make sure the .prj file is included in the zip."
)

# A "named frame" is (layer name, GeoDataFrame).
NamedFrame = tuple[str, gpd.GeoDataFrame]


def read_geofile(path: Path) -> gpd.GeoDataFrame:
    """Read a .kml or .zip (containing Shapefiles) into ONE GeoDataFrame."""
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".kml":
        frames = _read_kml(path)
    elif suffix == ".zip":
        frames = _read_zipped_shapefiles(path)
    else:
        raise GeoFileError(
            f"Unsupported file type '{suffix}'. Upload a .kml or a .zip containing a Shapefile."
        )

    return _combine(frames)


def _read_kml(path: Path) -> list[NamedFrame]:
    """Read every layer (KML <Folder>) in the file."""
    try:
        layer_names = [name for name, _ in list_layers(path)]
        return [(name, gpd.read_file(path, layer=name)) for name in layer_names]
    except Exception as exc:
        raise GeoFileError(f"Could not read KML file: {exc}") from exc


def _read_zipped_shapefiles(path: Path) -> list[NamedFrame]:
    """Read every .shp inside the zip."""
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

        frames: list[NamedFrame] = []
        for shp in shp_files:
            try:
                frames.append((shp.stem, gpd.read_file(shp)))
            except Exception as exc:
                raise GeoFileError(f"Could not read Shapefile '{shp.name}': {exc}") from exc
        return frames


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


def _combine(named_frames: list[NamedFrame]) -> gpd.GeoDataFrame:
    """Merge layers into one GeoDataFrame in a single, consistent CRS."""
    non_empty = [(name, gdf) for name, gdf in named_frames if len(gdf) > 0]
    if not non_empty:
        raise GeoFileError("The file contains no features.")
    if any(gdf.crs is None for _, gdf in non_empty):
        raise GeoFileError(NO_CRS_MESSAGE)

    target_crs = non_empty[0][1].crs
    several_sources = len(non_empty) > 1

    aligned = []
    for name, gdf in non_empty:
        if gdf.crs != target_crs:
            gdf = gdf.to_crs(target_crs)  # never mix coordinate systems
        if several_sources:
            gdf = gdf.assign(**{LAYER_COLUMN: name})  # remember where it came from
        aligned.append(gdf)

    combined = pd.concat(aligned, ignore_index=True)

    # KML often has a Z (altitude) value. Area/length are 2D, so drop Z.
    return combined.set_geometry(combined.geometry.force_2d())