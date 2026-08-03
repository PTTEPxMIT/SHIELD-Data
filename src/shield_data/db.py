"""SQLite database access for SHIELD experimental data.

The database itself is a build artifact. It is no longer committed to git or
shipped inside the package: CI rebuilds it whenever run data lands on main and
attaches it (gzipped, with a checksum manifest) to the rolling ``data-latest``
GitHub release. On first use this module downloads and caches that release;
call :func:`update_database` to pick up newly published runs.

Resolution order for the database path:

1. The ``SHIELD_DATA_DB`` environment variable (offline use, reproducible
   pipelines, or a custom build).
2. ``shield_data.db`` next to this file (a repo checkout where
   ``build_db.py`` has been run).
3. The cached download of the ``data-latest`` release (fetched on first use).
"""

import gzip
import hashlib
import json
import os
import platform
import sqlite3
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd

# Environment variable that pins the database to a local file.
DB_ENV_VAR = "SHIELD_DATA_DB"

# Rolling GitHub release that CI attaches the latest built database to.
DATA_RELEASE_URL = (
    "https://github.com/PTTEPxMIT/SHIELD-Data/releases/download/data-latest"
)

# Database sitting next to the source in a repo checkout (never present in an
# installed package).
_LOCAL_DB = Path(__file__).parent / "shield_data.db"

# Explicit override; tests monkeypatch this. None means "resolve on first use"
# via get_db_path().
DB_PATH: Path | None = None


def _cache_dir() -> Path:
    """Per-user cache directory for the downloaded database."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif platform.system() == "Darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "shield_data"


def _fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def update_database() -> Path:
    """Download the latest released database into the local cache.

    Fetches ``manifest.json`` from the ``data-latest`` GitHub release and
    downloads the gzipped database if the cached copy is missing or outdated.
    The SHA-256 checksum is verified before the cache is replaced, and the
    cached copy is left untouched if anything fails.

    Returns:
        Path to the cached database file
    """
    cache = _cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    db_file = cache / "shield_data.db"
    manifest_file = cache / "manifest.json"

    manifest = json.loads(_fetch(f"{DATA_RELEASE_URL}/manifest.json"))
    expected_sha = manifest["sha256"]

    if db_file.exists() and manifest_file.exists():
        cached = json.loads(manifest_file.read_text())
        if cached.get("sha256") == expected_sha:
            return db_file

    raw = gzip.decompress(_fetch(f"{DATA_RELEASE_URL}/shield_data.db.gz"))
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != expected_sha:
        raise RuntimeError(
            f"Downloaded database checksum mismatch: {actual_sha} != {expected_sha}"
        )

    tmp = db_file.with_suffix(".tmp")
    tmp.write_bytes(raw)
    tmp.replace(db_file)
    manifest_file.write_text(json.dumps(manifest))
    print(
        f"✓ shield_data: cached database with {manifest.get('runs', '?')} runs "
        f"at {db_file}"
    )
    return db_file


def get_db_path() -> Path:
    """Resolve the database path (see module docstring for the order)."""
    env = os.environ.get(DB_ENV_VAR)
    if env:
        path = Path(env)
        if not path.exists():
            raise FileNotFoundError(f"{DB_ENV_VAR} points to a missing file: {path}")
        return path
    if _LOCAL_DB.exists():
        return _LOCAL_DB
    cached = _cache_dir() / "shield_data.db"
    if cached.exists():
        return cached
    return update_database()


def _get_connection() -> sqlite3.Connection:
    """Get database connection with row factory."""
    conn = sqlite3.connect(DB_PATH or get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def catalogue() -> pd.DataFrame:
    """Load catalogue of all experimental runs.

    Returns:
        DataFrame with run metadata (run_id, date, run_type,
        furnace_setpoint, etc.)
    """
    with _get_connection() as conn:
        return pd.read_sql_query("SELECT * FROM runs", conn)


def load(run_id: str) -> pd.DataFrame:
    """Load pressure gauge data for a specific run.

    Args:
        run_id: The run ID (e.g., "25.10.06_run_1_10h41")

    Returns:
        DataFrame with timestamp and gauge voltage measurements
    """
    with _get_connection() as conn:
        return pd.read_sql_query(
            "SELECT * FROM measurements WHERE run_id = ?", conn, params=(run_id,)
        )


def load_metadata(run_id: str) -> dict[str, Any]:
    """Load metadata for a specific run.

    Args:
        run_id: The run ID

    Returns:
        Dictionary with run_info, gauges, and thermocouples
    """
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT metadata FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return json.loads(row["metadata"])


def load_filtered(**filters) -> pd.DataFrame:
    """Load data for runs matching filter criteria.

    Args:
        **filters: Column filters (e.g., run_type="permeation_exp",
                   furnace_setpoint=500)

    Returns:
        Combined DataFrame of all matching runs

    Example:
        >>> df = load_filtered(furnace_setpoint=500)
        >>> df = load_filtered(run_type="permeation_exp", date="2025-10-06")
    """
    cat = catalogue()

    # Apply filters
    for key, value in filters.items():
        if key not in cat.columns:
            raise ValueError(f"Unknown filter: {key}")
        cat = cat[cat[key] == value]

    if cat.empty:
        return pd.DataFrame()

    # Load all matching runs
    with _get_connection() as conn:
        placeholders = ",".join("?" * len(cat))
        query = f"SELECT * FROM measurements WHERE run_id IN ({placeholders})"
        return pd.read_sql_query(query, conn, params=tuple(cat["run_id"]))
