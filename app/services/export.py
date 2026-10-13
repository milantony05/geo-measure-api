"""Building the CSV export of a file's measurements."""
import csv
import io
import re
from collections.abc import Iterable

CSV_COLUMNS = [
    "feature_index",
    "name",
    "geometry_type",
    "measurement_type",
    "measurement_value",
    "measurement_unit",
    "source_layer",
    "note",
]

# Spreadsheet apps treat cells starting with these characters as formulas.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe_text(value) -> str:
    """Neutralise CSV/formula injection: prefix risky text with an apostrophe."""
    if value is None:
        return ""
    text = str(value)
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def measurements_to_csv(features: Iterable) -> str:
    """Return CSV text for feature objects (anything with the attributes used below)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)

    for feature in features:
        properties = feature.properties or {}
        name = properties.get("Name") or properties.get("name")
        writer.writerow(
            [
                feature.feature_index,
                _safe_text(name),
                feature.geometry_type or "",
                feature.measurement_type or "",
                "" if feature.measurement_value is None else feature.measurement_value,
                feature.measurement_unit or "",
                _safe_text(properties.get("source_layer")),
                _safe_text(feature.note),
            ]
        )
    return buffer.getvalue()


def csv_filename(original_name: str) -> str:
    """'My survey (1).kml' -> 'My_survey_1_measurements.csv' (safe for a header)."""
    stem = original_name.rsplit(".", 1)[0]
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "file"
    return f"{stem}_measurements.csv"