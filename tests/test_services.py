"""Unit tests for the CRS + measurement logic (no web server involved)."""
import geopandas as gpd
import pytest
from pyproj import Geod, Transformer
from shapely.geometry import GeometryCollection, MultiPolygon, Point, Polygon

from app.services.crs import crs_label, pick_projected_crs
from app.services.measure import measure_features
from app.services.errors import ReprojectionError
from app.services.reproject import make_reprojector


def square(lon: float, lat: float, size: float = 0.01) -> Polygon:
    return Polygon([(lon, lat), (lon + size, lat), (lon + size, lat + size), (lon, lat + size)])


def make_gdf(geometries) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"name": [f"f{i}" for i in range(len(geometries))]},
                            geometry=geometries, crs="EPSG:4326")


def test_picks_utm_zone_43_for_bengaluru():
    gdf = make_gdf([square(77.59, 12.97)])
    assert crs_label(pick_projected_crs(gdf)) == "EPSG:32643"


def test_polygon_area_is_in_square_metres_and_matches_geodesic():
    poly = square(77.59, 12.97)
    result = measure_features(make_gdf([poly]))

    feature = result.features[0]
    assert feature["measurement"]["type"] == "area"
    assert feature["measurement"]["unit"] == "m2"

    geodesic_area = abs(Geod(ellps="WGS84").geometry_area_perimeter(poly)[0])
    assert feature["measurement"]["value"] == pytest.approx(geodesic_area, rel=0.005)
    assert feature["measurement"]["value"] > 1_000_000  # square degrees would be ~0.0001


def test_linestring_length_in_metres():
    from shapely.geometry import LineString

    line = LineString([(77.59, 12.97), (77.60, 12.98)])
    result = measure_features(make_gdf([line]))

    geodesic_length = Geod(ellps="WGS84").geometry_length(line)
    measurement = result.features[0]["measurement"]
    assert measurement["type"] == "length"
    assert measurement["unit"] == "m"
    assert measurement["value"] == pytest.approx(geodesic_length, rel=0.005)


def test_point_has_no_measurement_and_no_note():
    result = measure_features(make_gdf([Point(77.595, 12.975)]))
    feature = result.features[0]
    assert feature["geometry_type"] == "Point"
    assert feature["measurement"] is None
    assert feature["note"] is None


def test_multipolygon_area_is_sum_of_parts():
    a, b = square(77.59, 12.97), square(77.61, 12.97)
    single = measure_features(make_gdf([a])).features[0]["measurement"]["value"]
    multi = measure_features(make_gdf([MultiPolygon([a, b])])).features[0]["measurement"]["value"]
    assert multi == pytest.approx(2 * single, rel=0.01)


def test_unsupported_geometry_is_handled_gracefully():
    collection = GeometryCollection([Point(77.59, 12.97), square(77.59, 12.97)])
    result = measure_features(make_gdf([collection]))
    feature = result.features[0]
    assert feature["geometry_type"] == "GeometryCollection"
    assert feature["measurement"] is None
    assert "not supported" in feature["note"]


def test_missing_geometry_does_not_crash():
    result = measure_features(make_gdf([None, square(77.59, 12.97)]))
    assert result.features[0]["geometry_type"] is None
    assert result.features[0]["note"] == "Feature has no geometry."
    assert result.features[1]["measurement"]["type"] == "area"


def test_original_geometry_and_crs_are_returned_not_projected():
    result = measure_features(make_gdf([Point(77.595, 12.975)]))
    feature = result.features[0]
    assert feature["crs"] == "EPSG:4326"
    assert feature["geometry"]["coordinates"] == [77.595, 12.975]


def test_reproject_utm_back_to_wgs84():
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
    x, y = to_utm.transform(77.595, 12.975)

    reproject, label = make_reprojector("EPSG:32643", "EPSG:4326")
    result = reproject({"type": "Point", "coordinates": [x, y]})

    assert label == "EPSG:4326"
    assert result["coordinates"] == pytest.approx((77.595, 12.975), abs=1e-6)


def test_reproject_to_same_crs_returns_geometry_unchanged():
    reproject, _ = make_reprojector("EPSG:4326", "EPSG:4326")
    geometry = {"type": "Point", "coordinates": [77.595, 12.975]}
    assert reproject(geometry) is geometry


def test_reproject_handles_missing_geometry():
    reproject, _ = make_reprojector("EPSG:32643", "EPSG:4326")
    assert reproject(None) is None


def test_reproject_with_invalid_crs_raises():
    with pytest.raises(ReprojectionError):
        make_reprojector("EPSG:4326", "not-a-crs")