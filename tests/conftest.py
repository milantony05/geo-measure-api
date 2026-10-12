"""Shared test setup."""
import shutil
from pathlib import Path

import geopandas as gpd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import LineString, Polygon
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401
from app.db import Base, get_db
from app.main import app

KML_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Sample survey</name>
    <Placemark>
      <name>Plot A</name>
      <Polygon><outerBoundaryIs><LinearRing><coordinates>
        77.590,12.970 77.600,12.970 77.600,12.980 77.590,12.980 77.590,12.970
      </coordinates></LinearRing></outerBoundaryIs></Polygon>
    </Placemark>
    <Placemark>
      <name>Road B</name>
      <LineString><coordinates>77.590,12.970 77.600,12.980</coordinates></LineString>
    </Placemark>
    <Placemark>
      <name>Gate C</name>
      <Point><coordinates>77.595,12.975</coordinates></Point>
    </Placemark>
  </Document>
</kml>
"""


@pytest.fixture
def client(tmp_path):
    """A test client wired to a brand-new temporary database."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    # Tell FastAPI: "whenever an endpoint asks for get_db, use ours instead."
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def kml_bytes() -> bytes:
    return KML_SAMPLE.encode("utf-8")


@pytest.fixture
def make_shapefile_zip(tmp_path):
    """Returns a function that builds a zipped shapefile and gives back its bytes."""

    def _make(with_prj: bool = True) -> bytes:
        folder = tmp_path / f"shp_{with_prj}"
        folder.mkdir()
        gdf = gpd.GeoDataFrame(
            {"name": ["Plot 1", "Plot 2"]},
            geometry=[
                Polygon([(77.590, 12.970), (77.600, 12.970), (77.600, 12.980), (77.590, 12.980)]),
                Polygon([(77.610, 12.970), (77.615, 12.970), (77.615, 12.975), (77.610, 12.975)]),
            ],
            crs="EPSG:4326",
        )
        gdf.to_file(folder / "plots.shp")
        if not with_prj:
            (folder / "plots.prj").unlink()
        archive = shutil.make_archive(str(tmp_path / f"plots_{with_prj}"), "zip", folder)
        return Path(archive).read_bytes()

    return _make


@pytest.fixture
def make_multi_shapefile_zip(tmp_path):
    """A zip with TWO shapefiles; the second one is stored in a different CRS."""

    def _make() -> bytes:
        folder = tmp_path / "multi_shp"
        folder.mkdir()

        plots = gpd.GeoDataFrame(
            {"name": ["Plot 1"]},
            geometry=[Polygon([(77.590, 12.970), (77.600, 12.970), (77.600, 12.980), (77.590, 12.980)])],
            crs="EPSG:4326",
        )
        roads = gpd.GeoDataFrame(
            {"name": ["Road 1"]},
            geometry=[LineString([(77.590, 12.970), (77.600, 12.980)])],
            crs="EPSG:4326",
        ).to_crs("EPSG:32643")  # store this one in UTM metres, not degrees

        plots.to_file(folder / "plots.shp")
        roads.to_file(folder / "roads.shp")
        archive = shutil.make_archive(str(tmp_path / "multi"), "zip", folder)
        return Path(archive).read_bytes()

    return _make