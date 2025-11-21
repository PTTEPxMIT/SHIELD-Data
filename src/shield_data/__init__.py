from importlib import metadata

try:
    __version__ = metadata.version("shield-data")
except Exception:
    __version__ = "unknown"

from shield_data.db import catalogue, load, load_filtered, load_metadata

__all__ = [
    "catalogue",
    "load",
    "load_filtered",
    "load_metadata",
]
