import geopandas as gpd

# ---- KML ----
print("=== KML ===")
kml = gpd.read_file("sample_data/sample.kml")
print(kml)
print("CRS:", kml.crs)
print("Geometry types:", kml.geom_type.tolist())

# ---- Shapefile inside a zip ----
print("\n=== SHAPEFILE ZIP ===")
shp = gpd.read_file("zip://sample_data/sample_shapefile.zip")
print(shp)
print("CRS:", shp.crs)

# ---- The WRONG way: measuring in degrees ----
print("\n=== WRONG: area in degrees ===")
print(shp.geometry.area.tolist(), "<- 'square degrees', meaningless!")

# ---- The RIGHT way: project to metres first ----
print("\n=== RIGHT: area in square metres ===")
utm_crs = shp.estimate_utm_crs()
print("Chosen projected CRS:", utm_crs.to_string())
projected = shp.to_crs(utm_crs)
print(projected.geometry.area.tolist(), "m²")

# ---- Lines ----
print("\n=== KML line length in metres ===")
kml_proj = kml.to_crs(kml.estimate_utm_crs())
for name, geom_type, geom in zip(kml_proj["Name"], kml_proj.geom_type, kml_proj.geometry):
    if geom_type == "LineString":
        print(name, "->", round(geom.length, 1), "m")