# Geospatial File Measurement API

A backend service that accepts a geospatial file (a zipped **Shapefile** or a **KML**), extracts every feature, and returns **area** (polygons) and **length** (lines) measurements in metric units.

Built with **FastAPI**, **GeoPandas / Shapely / PyProj**, and **SQLite (SQLAlchemy)**.

## Features

- Upload a `.kml` or a `.zip` containing a Shapefile
- Per-feature extraction: index, geometry type, geometry (GeoJSON), CRS and properties
- Polygon **area** (m²) and LineString **length** (m), computed in a **projected CRS** — never in degrees
- Unsupported or missing geometries are reported with a note instead of crashing the request
- Processing status tracking (`PROCESSING` → `COMPLETED` / `FAILED`) with stored error messages
- Interactive API docs at `/docs` (Swagger UI)
- Automated test suite (pytest)

## Setup

Requires **Python 3.10+** (developed and tested on 3.12).

**Windows (PowerShell)**

```powershell
git clone https://github.com/milantony05/geo-measure-api.git
cd geo-measure-api
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**macOS / Linux**

```bash
git clone https://github.com/milantony05/geo-measure-api.git
cd geo-measure-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API is now at http://127.0.0.1:8000 and the interactive docs at http://127.0.0.1:8000/docs.
A SQLite database file (`geo.db`) is created automatically on first start.

**Sample data:** run `python scripts/make_samples.py` to generate `sample_data/sample.kml` and `sample_data/sample_shapefile.zip`.

**Run the tests**

```bash
pytest -v
```

**Configuration (optional environment variables)**

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./geo.db` | SQLAlchemy database URL |
| `MAX_UPLOAD_MB` | `50` | Maximum accepted upload size |

## API

### `POST /api/files/` — upload and process a file

Accepts `multipart/form-data` with a `file` field (`.kml` or `.zip` containing a Shapefile).

```bash
curl -F "file=@sample_data/sample.kml" http://127.0.0.1:8000/api/files/
```

Response `201 Created`:

```json
{
  "id": "152c4053293640c999fb62c6cd52cfeb",
  "filename": "sample.kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "error": null,
  "created_at": "2026-10-12T12:01:12.281170"
}
```

### `GET /api/files/{id}/` — file information

```bash
curl http://127.0.0.1:8000/api/files/152c4053293640c999fb62c6cd52cfeb/
```

Returns the same object as the upload response (`200 OK`).

### `GET /api/files/{id}/measurements/` — per-feature measurements

```bash
curl http://127.0.0.1:8000/api/files/152c4053293640c999fb62c6cd52cfeb/measurements/
```

Response `200 OK` (shortened to two features; `properties` trimmed):

```json
{
  "id": "152c4053293640c999fb62c6cd52cfeb",
  "filename": "sample.kml",
  "crs": "EPSG:4326",
  "projected_crs": "EPSG:32643",
  "feature_count": 3,
  "features": [
    {
      "feature_index": 0,
      "geometry_type": "Polygon",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[77.59, 12.97], [77.6, 12.97], [77.6, 12.98], [77.59, 12.98], [77.59, 12.97]]]
      },
      "crs": "EPSG:4326",
      "properties": { "Name": "Plot A", "description": "A square polygon" },
      "measurement": { "type": "area", "value": 1201683.919, "unit": "m2" },
      "note": null
    },
    {
      "feature_index": 2,
      "geometry_type": "Point",
      "geometry": { "type": "Point", "coordinates": [77.595, 12.975] },
      "crs": "EPSG:4326",
      "properties": { "Name": "Gate C" },
      "measurement": null,
      "note": null
    }
  ]
}
```

- `geometry` is GeoJSON in the file's **original** CRS (`crs` field).
- `measurement` is `null` for points and for unsupported geometries; `note` explains why when relevant.

### Error responses

| Status | When |
|---|---|
| `400` | Unsupported file extension, or empty file |
| `404` | Unknown file id |
| `409` | Measurements requested for a file that is not `COMPLETED` |
| `413` | Upload larger than `MAX_UPLOAD_MB` |
| `422` | File could not be read (corrupt zip, no `.shp`, missing CRS, malformed KML). The failure is stored: `detail.file_id` can be used with `GET /api/files/{id}/` to see `status: FAILED` and the error message |
| `500` | Unexpected server error (also recorded as `FAILED`) |

## Architecture

### Application structure

```
app/
├── main.py            # FastAPI app, startup (creates tables), router registration
├── config.py          # Settings (upload size limit)
├── db.py              # SQLAlchemy engine / session
├── models.py          # Tables: files, features
├── schemas.py         # Pydantic response models
├── crud.py            # Database operations
├── api/
│   └── files.py       # HTTP endpoints (thin — no geospatial logic)
└── services/
    ├── errors.py      # GeoFileError (expected, user-caused failures)
    ├── reader.py      # KML / zipped Shapefile -> GeoDataFrame
    ├── crs.py         # Projected CRS selection
    └── measure.py     # Feature extraction + measurements
tests/                 # pytest: service-level and API-level tests
scripts/               # Sample data generator and exploration helpers
```

The API layer only handles HTTP concerns (validation, status codes). All geospatial logic lives in `services/`, so it can be tested without a web server.

### File-processing flow

1. **Validate**: extension must be `.kml` or `.zip`; the body must be non-empty and within the size limit.
2. **Save** the upload to a temporary directory under a fixed name (the user-supplied filename is never used as a path).
3. **Create** a `files` row with status `PROCESSING`.
4. **Read** the file with GeoPandas. For zips: safe extraction (zip-slip and size checks), then locate the `.shp`.
5. **Validate** the data: a CRS must be defined, there must be at least one feature, and Z values are dropped.
6. **Measure** every feature (below).
7. **Store** all features and set the status to `COMPLETED` in a **single transaction**. Any failure sets `FAILED` with an error message instead.
8. The temporary directory is deleted automatically.

### Measurement calculation flow

1. Choose one projected CRS for the whole file (see CRS handling).
2. Reproject a **copy** of the geometries into that CRS (units: metres).
3. For each feature:
   - `Polygon` / `MultiPolygon` → `area` in m²
   - `LineString` / `MultiLineString` → `length` in m
   - `Point` / `MultiPoint` → no measurement
   - anything else, or an empty geometry → no measurement and an explanatory `note`
   - invalid geometries (e.g. self-intersecting polygons) are measured but flagged in `note`
4. Return the **original, un-projected** geometry alongside the measurement.

### CRS handling

- KML is always WGS 84 (EPSG:4326). Shapefiles carry their CRS in the `.prj` file.
- Degrees are never used for measurement (1° of longitude shrinks towards the poles).
- The UTM zone that best fits the data is chosen with `GeoDataFrame.estimate_utm_crs()` (for example, Bengaluru → EPSG:32643). Data in any input CRS (geographic or projected) is first reprojected to that UTM zone.
- The projected copy is used only to calculate; responses always contain the user's original coordinates and CRS.

## Design decisions

| Decision | Choice | Alternatives considered / reasoning |
|---|---|---|
| Framework | **FastAPI** | Django + DRF would add ORM/admin/settings boilerplate that this small, API-only service doesn't need. FastAPI gives typed request/response models and automatic OpenAPI docs. |
| Projected CRS | **Best-fit UTM zone per file** | An equal-area projection (e.g. Albers / Mollweide) is better for very large extents; a geodesic calculation (`pyproj.Geod`) has no zone distortion at all. UTM is metric, standard, and accurate for survey-scale data. I cross-checked against geodesic results: for the sample data they differ by ~0.12%, which is expected projection distortion. |
| Files without a CRS | **Rejected (422)** | Assuming EPSG:4326 could silently produce wrong measurements for data that is actually in a projected CRS. |
| Original vs projected geometry in responses | **Original** | GeoJSON consumers expect lon/lat; the projection is an internal calculation detail and differs per file. |
| Unsupported geometries | **Reported with a `note`** | Failing the whole upload because of one feature would make files unusable. |
| Processing model | **Synchronous, with status lifecycle** | Fine for typical survey files. The `PROCESSING/COMPLETED/FAILED` status and stored errors make it straightforward to move to a background worker later. |
| Storage | **SQLite + SQLAlchemy; geometry as GeoJSON in a JSON column** | PostgreSQL/PostGIS would enable spatial queries but adds setup friction, and this service never queries spatially. `DATABASE_URL` makes switching databases easy. |
| Atomic saves | **One transaction for all features + final status** | A file can never be `COMPLETED` with missing features. |
| IDs | **Random UUIDs** | Sequential ids are guessable. |
| Security | Zip-slip and zip-bomb checks, upload size limit, temp directory, no user-supplied paths | Uploaded archives are untrusted input. |
| Endpoint style | **Plain `def` endpoints** | GeoPandas is blocking and CPU-bound; FastAPI runs sync endpoints in a thread pool so the event loop is not blocked. |

## Known limitations

- Only the **first `.shp`** in a zip is processed.
- Only the **first layer** of a KML is read (KML folders map to layers).
- One UTM zone is used per file, so measurements for files spanning several zones are less accurate.
- `created_at` is returned without a timezone suffix because SQLite does not store timezones.
- Processing is synchronous; very large files will hold the request open.

## Learning and future scope

### What I learned

- I learned why geospatial measurements cannot be calculated directly from latitude and longitude in degrees, and how using a suitable projected CRS such as UTM allows areas and lengths to be calculated in metres. I also learned why the original coordinates should be preserved in the API response.
- I learned how to build a file-processing API using FastAPI, GeoPandas and Shapely, from validating KML and zipped Shapefile uploads to extracting individual features and returning their measurements as structured JSON.
- I learned the importance of handling errors and tracking processing status. Instead of treating every failure the same way, the API uses appropriate HTTP status codes and records whether processing completed or failed, along with the error message.
- I gained a better understanding of file-upload security, including upload size limits, safe ZIP extraction, protection against path traversal attacks (zip-slip), and avoiding the use of user-supplied filenames as filesystem paths.
- I learned to separate API endpoints from geospatial processing logic and database operations, making the application easier to test and maintain. I also learned the importance of database transactions to prevent a file from being marked as completed when its features have not all been stored successfully.
- With more time, I would explore background processing for large uploads, support multiple Shapefiles and KML layers, and compare projected measurements with geodesic calculations across datasets covering larger geographical areas.

### Future scope

- Background processing (Celery/RQ + Redis) with polling or webhooks
- PostgreSQL + PostGIS for spatial queries
- Authentication and per-user file ownership
- Read all KML layers and multiple shapefiles per archive
- Pagination and filtering on the measurements endpoint
- GeoJSON and GeoPackage upload support
- Geodesic measurement option