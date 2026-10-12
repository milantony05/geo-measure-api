import json

from pyproj import Geod

from app.services.measure import measure_features
from app.services.reader import read_geofile

# --- KML ---
result = measure_features(read_geofile("sample_data/sample.kml"))
print("Source CRS:", result.source_crs, "| Projected CRS:", result.projected_crs)
print(json.dumps(result.features, indent=2)[:1500], "...\n")

# --- Shapefile + a sanity check with a different method ---
gdf = read_geofile("sample_data/sample_shapefile.zip")
result = measure_features(gdf)
geod = Geod(ellps="WGS84")  # measures directly on the Earth's curved surface

for feature, geom in zip(result.features, gdf.geometry):
    utm_area = feature["measurement"]["value"]
    geodesic_area = abs(geod.geometry_area_perimeter(geom)[0])
    diff_pct = (utm_area - geodesic_area) / geodesic_area * 100
    print(f"{feature['properties']['name']}: UTM={utm_area:,.0f}  geodesic={geodesic_area:,.0f}  diff={diff_pct:.3f}%")

# --- Error handling ---
from app.services.errors import GeoFileError
try:
    read_geofile("requirements.txt")
except GeoFileError as e:
    print("\nCaught expected error:", e)