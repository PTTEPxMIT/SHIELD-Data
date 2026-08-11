from importlib import metadata

try:
    __version__ = metadata.version("shield-data")
except Exception:
    __version__ = "unknown"

from shield_data.db import (
    catalogue,
    get_db_path,
    load,
    load_filtered,
    load_metadata,
    update_catalogue,
    update_database,
)

__all__ = [
    "catalogue",
    "get_db_path",
    "load",
    "load_filtered",
    "load_metadata",
    "update_catalogue",
    "update_database",
]
