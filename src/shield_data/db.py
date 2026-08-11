"""Access to SHIELD experimental runs: per-run Parquet with a small catalogue.

Runs are stored one Parquet file per run under ``run_data/`` in the git repo
(see :mod:`shield_data.store`). Consumers no longer download the whole
dataset: :func:`catalogue` reads a small catalogue file (built by CI and
attached to the rolling ``data-latest`` release), and :func:`load` fetches
just the requested run from the repository, verifies its sha256 against the
catalogue, and caches it in a per-user cache directory.

Resolution order in this default "store" mode:

1. A repo checkout: if ``run_data/`` exists next to the package source, runs
   are read straight from disk and the catalogue is built on the fly.
2. The per-user cache of previously fetched runs and catalogue.
3. Download: the catalogue from the ``data-latest`` release
   (:func:`update_catalogue` refreshes it), individual runs from the
   repository's raw URLs.

Legacy mode: pinning a database via the ``SHIELD_DATA_DB`` environment
variable (or the ``DB_PATH`` module attribute) preserves the original SQLite
behaviour exactly — including the old ``timestamp`` / ``*_voltage`` column
names — for reproducible pipelines that predate per-run storage. This path
is deprecated and will be removed once downstream consumers migrate.
"""

import gzip
import hashlib
import json
import os
import platform
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd

from shield_data import store

# Environment variables pinning local files (legacy DB pin enables legacy mode).
DB_ENV_VAR = "SHIELD_DATA_DB"
CATALOGUE_ENV_VAR = "SHIELD_DATA_CATALOGUE"

# Rolling GitHub release that CI attaches the catalogue (and, during the
# deprecation window, the legacy database) to.
DATA_RELEASE_URL = (
    "https://github.com/PTTEPxMIT/SHIELD-Data/releases/download/data-latest"
)

# Individual runs are fetched per-file from the repository itself.
RAW_DATA_URL = "https://raw.githubusercontent.com/PTTEPxMIT/SHIELD-Data/main/run_data"

# Repo-checkout locations (never present in an installed package).
_LOCAL_DB = Path(__file__).parent / "shield_data.db"
_REPO_RUN_DATA = Path(__file__).parents[2] / "run_data"

# Explicit overrides; tests monkeypatch these. None means "resolve on use".
DB_PATH: Path | None = None
RUN_DATA_DIR: Path | None = None
CATALOGUE_PATH: Path | None = None

# Per-process memo of catalogues built from a local run_data checkout.
_CATALOGUE_MEMO: dict[str, pd.DataFrame] = {}


def _legacy_mode() -> bool:
    """True when a SQLite database is explicitly pinned (legacy behaviour)."""
    return DB_PATH is not None or bool(os.environ.get(DB_ENV_VAR))


def _cache_dir() -> Path:
    """Per-user cache directory for downloaded runs and catalogue."""
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


def update_catalogue() -> Path:
    """Download the latest released catalogue into the local cache.

    Fetches ``manifest.json`` from the ``data-latest`` GitHub release and
    downloads ``catalogue.parquet`` if the cached copy is missing or
    outdated. The sha256 is verified before the cache is replaced.

    Returns:
        Path to the cached catalogue file
    """
    cache = _cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    cat_file = cache / store.CATALOGUE_FILENAME
    manifest_file = cache / "catalogue_manifest.json"

    manifest = json.loads(_fetch(f"{DATA_RELEASE_URL}/manifest.json"))
    expected_sha = manifest.get("catalogue_sha256")
    if not expected_sha:
        raise RuntimeError(
            "The data-latest release does not include a catalogue yet; "
            "use update_database() until one is published."
        )

    if cat_file.exists() and manifest_file.exists():
        cached = json.loads(manifest_file.read_text())
        if cached.get("catalogue_sha256") == expected_sha:
            return cat_file

    raw = _fetch(f"{DATA_RELEASE_URL}/{store.CATALOGUE_FILENAME}")
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != expected_sha:
        raise RuntimeError(
            f"Downloaded catalogue checksum mismatch: {actual_sha} != {expected_sha}"
        )

    tmp = cat_file.with_suffix(".tmp")
    tmp.write_bytes(raw)
    tmp.replace(cat_file)
    manifest_file.write_text(json.dumps(manifest))
    print(f"✓ shield_data: cached catalogue ({manifest.get('runs', '?')} runs)")
    return cat_file


def _run_data_dir() -> Path | None:
    """Local run_data checkout, if there is one."""
    d = RUN_DATA_DIR if RUN_DATA_DIR is not None else _REPO_RUN_DATA
    return d if d.is_dir() else None


def _store_catalogue() -> pd.DataFrame | None:
    """The catalogue in store mode: local checkout, pin, cache, or download."""
    data_dir = _run_data_dir()
    if data_dir is not None:
        key = str(data_dir.resolve())
        if key not in _CATALOGUE_MEMO:
            _CATALOGUE_MEMO[key] = store.build_catalogue(data_dir)
        return _CATALOGUE_MEMO[key].copy()

    pin = os.environ.get(CATALOGUE_ENV_VAR) or CATALOGUE_PATH
    if pin:
        path = Path(pin)
        if not path.exists():
            raise FileNotFoundError(f"Pinned catalogue is missing: {path}")
        return pd.read_parquet(path)

    cached = _cache_dir() / store.CATALOGUE_FILENAME
    if cached.exists():
        return pd.read_parquet(cached)

    try:
        return pd.read_parquet(update_catalogue())
    except (urllib.error.URLError, RuntimeError, OSError):
        return None


def _ensure_cached_run(run_id: str) -> Path:
    """Return the run's cached data file, downloading it if necessary."""
    run_cache = _cache_dir() / "runs" / run_id
    for name in (store.MEASUREMENTS_FILENAME, store.LEGACY_CSV_FILENAME):
        if (run_cache / name).exists():
            return run_cache / name

    cat = _store_catalogue()
    expected_sha = None
    candidates = [store.MEASUREMENTS_FILENAME, store.LEGACY_CSV_FILENAME]
    if cat is not None:
        row = cat[cat["run_id"] == run_id]
        if not row.empty:
            candidates = [row.iloc[0]["data_file"]]
            expected_sha = row.iloc[0]["sha256"]

    for name in candidates:
        try:
            raw = _fetch(f"{RAW_DATA_URL}/{run_id}/{name}")
        except urllib.error.HTTPError as err:
            if err.code == 404:
                continue
            raise
        if expected_sha and hashlib.sha256(raw).hexdigest() != expected_sha:
            raise RuntimeError(
                f"Downloaded {run_id}/{name} does not match the catalogue "
                "checksum. The catalogue may be stale: run "
                "shield_data.update_catalogue() and retry."
            )
        run_cache.mkdir(parents=True, exist_ok=True)
        tmp = run_cache / (name + ".tmp")
        tmp.write_bytes(raw)
        tmp.replace(run_cache / name)
        return run_cache / name

    raise FileNotFoundError(
        f"Run {run_id!r} was not found locally, in the cache, or at "
        f"{RAW_DATA_URL}/{run_id}/"
    )


# --- legacy SQLite path (active only when a database is pinned) -------------


def update_database() -> Path:
    """Download the latest released legacy database into the local cache.

    Deprecated: per-run Parquet access via :func:`load` needs no database.
    Kept while downstream consumers migrate.

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
    """Resolve the legacy database path (env pin, checkout, cache, download)."""
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
    """Get legacy database connection with row factory."""
    conn = sqlite3.connect(DB_PATH or get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


# --- public API -------------------------------------------------------------


def catalogue() -> pd.DataFrame:
    """Load the catalogue of all experimental runs.

    In store mode the catalogue has one row per run with normalised metadata
    fields (date, start_time, end_time, run_type, furnace_setpoint,
    substrate, coating), the list of recorded ``channels``,
    ``n_measurements``, and the data file's checksum. The coating is a
    human-readable summary (e.g. "800nm tungsten", "none" for uncoated); the
    per-layer breakdown lives in the run metadata's
    ``sample_coating_layers``. With a pinned database (legacy mode) it is
    the old SQLite ``runs`` table, which keeps its ``material`` column.

    Returns:
        DataFrame with one row per run
    """
    if not _legacy_mode():
        cat = _store_catalogue()
        if cat is not None:
            return cat
    with _get_connection() as conn:
        return pd.read_sql_query("SELECT * FROM runs", conn)


def load(run_id: str) -> pd.DataFrame:
    """Load the measurements of a specific run.

    Store mode returns the channels exactly as the rig recorded them —
    ``RealTimestamp`` (datetime64) plus every recorded column, e.g.
    ``WGM701_Voltage (V)`` or ``Local_temperature (C)`` — with a ``run_id``
    column appended. Only this run's file is downloaded (and cached); the
    download is verified against the catalogue's sha256.

    Legacy mode (pinned database) keeps the old ``timestamp`` /
    ``*_voltage`` columns.

    Args:
        run_id: The run ID (e.g., "25.10.06_run_1_10h41")

    Returns:
        DataFrame with one row per measurement
    """
    if not _legacy_mode():
        data_dir = _run_data_dir()
        if data_dir is not None and (data_dir / run_id).is_dir():
            df = store.read_measurements(data_dir / run_id)
        else:
            df = store.read_measurements(_ensure_cached_run(run_id).parent)
        df["run_id"] = run_id
        return df
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
    if not _legacy_mode():
        cat = _store_catalogue()
        if cat is not None:
            row = cat[cat["run_id"] == run_id]
            if row.empty:
                raise KeyError(f"Run {run_id!r} is not in the catalogue")
            return json.loads(row.iloc[0]["metadata"])
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT metadata FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return json.loads(row["metadata"])


def load_filtered(**filters) -> pd.DataFrame:
    """Load data for runs matching filter criteria.

    Filters apply to catalogue columns, so any normalised metadata field
    works (substrate, coating, furnace_setpoint, run_type, date, ...). In
    store mode only the matching runs are downloaded; columns are aligned
    across runs, with NaN where a run did not record a channel.

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

    if not _legacy_mode():
        return pd.concat([load(run_id) for run_id in cat["run_id"]], ignore_index=True)

    # Load all matching runs
    with _get_connection() as conn:
        placeholders = ",".join("?" * len(cat))
        query = f"SELECT * FROM measurements WHERE run_id IN ({placeholders})"
        return pd.read_sql_query(query, conn, params=tuple(cat["run_id"]))
