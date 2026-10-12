from app import crud
from app.db import Base, SessionLocal, engine
from app import models  # noqa: F401
from app.services.measure import measure_features
from app.services.reader import read_geofile

Base.metadata.create_all(bind=engine)

db = SessionLocal()
try:
    file = crud.create_file(db, "sample.kml")
    print("Created:", file.id, file.status)

    result = measure_features(read_geofile("sample_data/sample.kml"))
    crud.save_result(db, file, result)

    # Fetch it back as if a brand-new request came in
    fetched = crud.get_file(db, file.id)
    print("Fetched:", fetched.filename, fetched.status, fetched.crs, fetched.feature_count)
    for f in fetched.features:
        print(" ", f.feature_index, f.geometry_type, f.measurement_type, f.measurement_value, f.measurement_unit)
finally:
    db.close()