class GeoFileError(Exception):
    """Raised when an uploaded file is invalid or can't be processed.

    The API layer will catch this and turn it into a clean 4xx response
    instead of letting the server crash with a 500.
    """


class ReprojectionError(Exception):
    """Raised when a CRS is invalid or a geometry can't be reprojected."""