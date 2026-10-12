class GeoFileError(Exception):
    """Raised when an uploaded file is invalid or can't be processed.

    The API layer will catch this and turn it into a clean 4xx response
    instead of letting the server crash with a 500.
    """