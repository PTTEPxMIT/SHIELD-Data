"""SQLite database access for SHIELD experimental data."""

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

# Database bundled with the package
DB_PATH = Path(__file__).parent / "shield_data.db"


def _get_connection() -> sqlite3.Connection:
    """Get database connection with row factory."""
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found at {DB_PATH}. "
            "The package may not be properly installed."
        )
    conn = sqlite3.connect(DB_PATH)
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
        df = pd.read_sql_query(
            "SELECT * FROM measurements WHERE run_id = ?", conn, params=(run_id,)
        )
        if df.empty:
            raise ValueError(f"No data found for run_id: {run_id}")
        return df


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
        if not row:
            raise ValueError(f"No metadata found for run_id: {run_id}")
        import json

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
