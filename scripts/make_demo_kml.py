"""Generates a richer demo KML (several polygons, lines and points near Bengaluru)."""
from pathlib import Path

POLYGONS = {
    "North field": [(77.5920, 12.9860), (77.5990, 12.9880), (77.6010, 12.9830), (77.5950, 12.9800), (77.5920, 12.9860)],
    "Reservoir": [(77.6040, 12.9760), (77.6100, 12.9780), (77.6130, 12.9730), (77.6070, 12.9700), (77.6030, 12.9720), (77.6040, 12.9760)],
    "South plot": [(77.5880, 12.9700), (77.5940, 12.9710), (77.5950, 12.9650), (77.5890, 12.9640), (77.5880, 12.9700)],
}
LINES = {
    "Access road": [(77.5850, 12.9780), (77.5930, 12.9770), (77.6000, 12.9760), (77.6035, 12.9745)],
    "Pipeline": [(77.5960, 12.9800), (77.5985, 12.9740), (77.5955, 12.9700)],
}
POINTS = {
    "Main gate": (77.5850, 12.9780),
    "Pump house": (77.6035, 12.9745),
    "Survey marker": (77.5920, 12.9860),
}


def coords(points) -> str:
    return " ".join(f"{lon},{lat}" for lon, lat in points)


placemarks = []
for name, ring in POLYGONS.items():
    placemarks.append(
        f"<Placemark><name>{name}</name><Polygon><outerBoundaryIs><LinearRing>"
        f"<coordinates>{coords(ring)}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>"
    )
for name, line in LINES.items():
    placemarks.append(
        f"<Placemark><name>{name}</name><LineString><coordinates>{coords(line)}</coordinates></LineString></Placemark>"
    )
for name, (lon, lat) in POINTS.items():
    placemarks.append(
        f"<Placemark><name>{name}</name><Point><coordinates>{lon},{lat}</coordinates></Point></Placemark>"
    )

kml = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Demo survey</name>\n'
    + "\n".join(placemarks)
    + "\n</Document></kml>\n"
)

out = Path("sample_data/demo_survey.kml")
out.parent.mkdir(exist_ok=True)
out.write_text(kml, encoding="utf-8")
print("Created", out)