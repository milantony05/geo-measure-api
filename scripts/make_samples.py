"""Generates small sample files (KML + zipped Shapefile) around Bengaluru."""
import shutil
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

OUT = Path("sample_data")
OUT.mkdir(exist_ok=True)

# 1. KML
# NOTE: KML coordinates are "longitude,latitude"
kml = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Sample survey</name>
    <Placemark>
      <name>Plot A</name>
      <description>A square polygon</description>
      <Polygon><outerBoundaryIs><LinearRing><coordinates>
        77.590,12.970 77.600,12.970 77.600,12.980 77.590,12.980 77.590,12.970
      </coordinates></LinearRing></outerBoundaryIs></Polygon>
    </Placemark>
    <Placemark>
      <name>Road B</name>
      <LineString><coordinates>
        77.590,12.970 77.600,12.980
      </coordinates></LineString>
    </Placemark>
    <Placemark>
      <name>Gate C</name>
      <Point><coordinates>77.595,12.975</coordinates></Point>
    </Placemark>
  </Document>
</kml>
"""
(OUT / "sample.kml").write_text(kml, encoding="utf-8")

# 2. Shapefile (polygons only) zipped
# A shapefile can hold only ONE geometry type, so we use polygons here.
gdf = gpd.GeoDataFrame(
    {
        "name": ["Plot 1", "Plot 2"],
        "owner": ["Milan", "Akshay"],
    },
    geometry=[
        Polygon([(77.590, 12.970), (77.600, 12.970), (77.600, 12.980), (77.590, 12.980)]),
        Polygon([(77.610, 12.970), (77.615, 12.970), (77.615, 12.975), (77.610, 12.975)]),
    ],
    crs="EPSG:4326",
)

shp_dir = OUT / "shp_tmp"
shp_dir.mkdir(exist_ok=True)
gdf.to_file(shp_dir / "plots.shp")                      # creates .shp .shx .dbf .prj ...
shutil.make_archive(str(OUT / "sample_shapefile"), "zip", shp_dir)
shutil.rmtree(shp_dir)

print("Created:", [p.name for p in OUT.iterdir()])