"""End-to-end tests: real HTTP requests against the app."""
import pytest


def upload(client, name: str, content: bytes):
    return client.post("/api/files/", files={"file": (name, content, "application/octet-stream")})


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_upload_kml(client, kml_bytes):
    response = upload(client, "survey.kml", kml_bytes)
    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "survey.kml"
    assert body["status"] == "COMPLETED"
    assert body["feature_count"] == 3
    assert body["crs"] == "EPSG:4326"


def test_get_file_info(client, kml_bytes):
    file_id = upload(client, "survey.kml", kml_bytes).json()["id"]
    response = client.get(f"/api/files/{file_id}/")
    assert response.status_code == 200
    assert response.json()["id"] == file_id
    assert response.json()["feature_count"] == 3


def test_measurements_for_kml(client, kml_bytes):
    file_id = upload(client, "survey.kml", kml_bytes).json()["id"]
    response = client.get(f"/api/files/{file_id}/measurements/")
    assert response.status_code == 200
    body = response.json()
    assert body["projected_crs"] == "EPSG:32643"

    by_type = {f["geometry_type"]: f for f in body["features"]}
    assert by_type["Polygon"]["measurement"]["value"] == pytest.approx(1_200_290, rel=0.005)
    assert by_type["LineString"]["measurement"]["unit"] == "m"
    assert by_type["Point"]["measurement"] is None
    assert by_type["Polygon"]["crs"] == "EPSG:4326"
    assert by_type["Polygon"]["properties"]["Name"] == "Plot A"


def test_upload_zipped_shapefile(client, make_shapefile_zip):
    response = upload(client, "plots.zip", make_shapefile_zip())
    assert response.status_code == 201
    assert response.json()["feature_count"] == 2

    file_id = response.json()["id"]
    features = client.get(f"/api/files/{file_id}/measurements/").json()["features"]
    assert all(f["measurement"]["type"] == "area" for f in features)
    assert features[0]["properties"]["name"] == "Plot 1"


def test_unsupported_extension_is_rejected(client):
    response = upload(client, "notes.txt", b"hello")
    assert response.status_code == 400


def test_empty_file_is_rejected(client):
    response = upload(client, "empty.kml", b"")
    assert response.status_code == 400


def test_file_too_large_is_rejected(client, kml_bytes, monkeypatch):
    monkeypatch.setattr("app.api.files.MAX_UPLOAD_BYTES", 10)  # pretend limit is 10 bytes
    response = upload(client, "survey.kml", kml_bytes)
    assert response.status_code == 413


def test_invalid_zip_is_recorded_as_failed(client):
    response = upload(client, "fake.zip", b"definitely not a zip")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["status"] == "FAILED"

    info = client.get(f"/api/files/{detail['file_id']}/").json()
    assert info["status"] == "FAILED"
    assert info["error"]


def test_measurements_of_failed_file_returns_409(client):
    detail = upload(client, "fake.zip", b"nope").json()["detail"]
    response = client.get(f"/api/files/{detail['file_id']}/measurements/")
    assert response.status_code == 409


def test_shapefile_without_prj_is_rejected(client, make_shapefile_zip):
    response = upload(client, "plots.zip", make_shapefile_zip(with_prj=False))
    assert response.status_code == 422
    assert "CRS" in response.json()["detail"]["message"]


def test_malformed_kml_fails_gracefully(client):
    response = upload(client, "broken.kml", b"<kml><oops")
    assert response.status_code == 422


def test_unknown_id_returns_404(client):
    assert client.get("/api/files/nope/").status_code == 404
    assert client.get("/api/files/nope/measurements/").status_code == 404


MULTI_FOLDER_KML = b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Folder>
      <name>North</name>
      <Placemark><name>N1</name><Point><coordinates>77.590,13.050</coordinates></Point></Placemark>
      <Placemark><name>N2</name>
        <LineString><coordinates>77.590,13.050 77.600,13.060</coordinates></LineString>
      </Placemark>
    </Folder>
    <Folder>
      <name>South</name>
      <Placemark><name>S1</name>
        <Polygon><outerBoundaryIs><LinearRing><coordinates>
          77.590,12.970 77.600,12.970 77.600,12.980 77.590,12.980 77.590,12.970
        </coordinates></LinearRing></outerBoundaryIs></Polygon>
      </Placemark>
    </Folder>
  </Document>
</kml>
"""


def test_kml_with_multiple_folders_reads_every_feature(client):
    response = upload(client, "folders.kml", MULTI_FOLDER_KML)
    assert response.status_code == 201
    assert response.json()["feature_count"] == 3  # not just the first folder!

    features = client.get(f"/api/files/{response.json()['id']}/measurements/").json()["features"]
    layers = {f["properties"]["Name"]: f["properties"]["source_layer"] for f in features}
    assert layers == {"N1": "North", "N2": "North", "S1": "South"}


def test_single_layer_file_has_no_source_layer_property(client, kml_bytes):
    file_id = upload(client, "survey.kml", kml_bytes).json()["id"]
    features = client.get(f"/api/files/{file_id}/measurements/").json()["features"]
    assert all("source_layer" not in f["properties"] for f in features)


def test_zip_with_multiple_shapefiles_in_different_crs(client, make_multi_shapefile_zip):
    response = upload(client, "multi.zip", make_multi_shapefile_zip())
    assert response.status_code == 201
    assert response.json()["feature_count"] == 2

    body = client.get(f"/api/files/{response.json()['id']}/measurements/").json()
    by_type = {f["geometry_type"]: f for f in body["features"]}

    assert {f["properties"]["source_layer"] for f in body["features"]} == {"plots", "roads"}
    assert body["crs"] == "EPSG:4326"  # the UTM roads were reprojected to match plots
    assert by_type["LineString"]["measurement"]["value"] == pytest.approx(1550.4, rel=0.01)
    assert by_type["Polygon"]["measurement"]["value"] == pytest.approx(1_200_290, rel=0.005)


def test_measurements_can_be_returned_in_another_crs(client, kml_bytes):
    file_id = upload(client, "survey.kml", kml_bytes).json()["id"]
    body = client.get(f"/api/files/{file_id}/measurements/?crs=EPSG:3857").json()

    by_type = {f["geometry_type"]: f for f in body["features"]}
    point = by_type["Point"]
    assert point["crs"] == "EPSG:3857"
    assert abs(point["geometry"]["coordinates"][0]) > 1_000_000  # metres, not degrees

    # Measurements must not change just because the geometry was reprojected.
    assert by_type["Polygon"]["measurement"]["value"] == pytest.approx(1_200_290, rel=0.005)


def test_measurements_with_invalid_crs_returns_400(client, kml_bytes):
    file_id = upload(client, "survey.kml", kml_bytes).json()["id"]
    response = client.get(f"/api/files/{file_id}/measurements/?crs=nonsense")
    assert response.status_code == 400