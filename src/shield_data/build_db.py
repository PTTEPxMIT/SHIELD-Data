"""Build the legacy SQLite database from the run_data folder.

Deprecated: runs are now stored and served as per-run Parquet files (see
shield_data.store). This builder is kept while downstream consumers migrate
off the monolithic database; it reads either storage format. Note the
measurements table keeps only the four original gauge-voltage columns —
additional channels (e.g. temperatures) are available via the Parquet path.
"""

import argparse
import json
import sqlite3
from pathlib import Path

import pandas as pd

from shield_data import store

# CSV columns (with units, as written by SHIELD_DAS) in measurement-table order.
_MEASUREMENT_CSV_COLUMNS = [
    "RealTimestamp",
    "WGM701_Voltage (V)",
    "CVM211_Voltage (V)",
    "Baratron626D_1KT_Voltage (V)",
    "Baratron626D_1T_Voltage (V)",
]


def _default_output() -> Path:
    return Path(__file__).parent / "shield_data.db"


def _create_schema(cursor: sqlite3.Cursor) -> None:
    """Create tables and indexes if they do not already exist."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            date TEXT,
            start_time TEXT,
            run_type TEXT,
            furnace_setpoint INTEGER,
            material TEXT,
            coating TEXT,
            metadata TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            timestamp TEXT,
            WGM701_voltage REAL,
            CVM211_voltage REAL,
            Baratron626D_1KT_voltage REAL,
            Baratron626D_1T_voltage REAL,
            FOREIGN KEY (run_id) REFERENCES runs(run_id)
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_run_id ON measurements(run_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_date ON runs(date)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_furnace_setpoint ON runs(furnace_setpoint)"
    )


def _insert_run(cursor: sqlite3.Cursor, run_folder: Path) -> int:
    """Insert one run folder's metadata and measurements.

    Any existing rows for the same run_id are replaced, so re-inserting a run
    (e.g. after a re-upload with more data) is safe and idempotent.

    Args:
        cursor: Cursor on the target database (schema must already exist)
        run_folder: Run directory containing run_metadata.json and
            pressure_gauge_data.csv

    Returns:
        Number of measurement rows inserted
    """
    run_id = run_folder.name
    metadata_file = run_folder / "run_metadata.json"

    with open(metadata_file) as f:
        metadata = json.load(f)

    run_info = metadata.get("run_info", {})

    cursor.execute("DELETE FROM measurements WHERE run_id = ?", (run_id,))
    cursor.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))

    cursor.execute(
        """
        INSERT INTO runs (run_id, date, start_time, run_type,
                        furnace_setpoint, material, coating, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            run_id,
            run_info.get("date"),
            run_info.get("start_time"),
            run_info.get("run_type"),
            run_info.get("furnace_setpoint"),
            # v1.0 metadata calls this "material", v1.3 "sample_material"
            run_info.get("material", run_info.get("sample_material")),
            run_info.get("coating"),
            json.dumps(metadata),
        ),
    )

    csv_file = run_folder / store.LEGACY_CSV_FILENAME
    if csv_file.exists():
        df = pd.read_csv(csv_file)
    else:
        df = store.read_measurements(run_folder)
        # The measurements table stores timestamps as text in the format the
        # rig originally wrote (millisecond precision).
        df[store.TIMESTAMP_COLUMN] = (
            df[store.TIMESTAMP_COLUMN].dt.strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3]
        )
    columns = [
        df[name].where(pd.notna(df[name]), None)
        if name in df.columns
        else [None] * len(df)
        for name in _MEASUREMENT_CSV_COLUMNS
    ]
    measurements = list(zip([run_id] * len(df), *columns))

    cursor.executemany(
        """
        INSERT INTO measurements
        (run_id, timestamp, WGM701_voltage, CVM211_voltage,
         Baratron626D_1KT_voltage, Baratron626D_1T_voltage)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        measurements,
    )

    return len(measurements)


def add_run(run_dir: str | Path, output: str | Path | None = None) -> int:
    """Add (or replace) a single run in the database without a full rebuild.

    Creates the database and schema if they do not exist yet. If the run is
    already present it is replaced, leaving all other runs untouched.

    Args:
        run_dir: Path to one run folder (run_data/YY.MM.DD_run_X_HHhMM)
        output: Database path (default: src/shield_data/shield_data.db)

    Returns:
        Number of measurement rows inserted
    """
    run_dir = Path(run_dir)
    output = _default_output() if output is None else Path(output)

    conn = sqlite3.connect(output)
    try:
        cursor = conn.cursor()
        _create_schema(cursor)
        count = _insert_run(cursor, run_dir)
        conn.commit()
    finally:
        conn.close()

    print(f"✓ {run_dir.name}: {count} measurements")
    return count


def build_database(data_dir: str | Path = "run_data", output: str | Path | None = None):
    """Build SQLite database from run data folder.

    Args:
        data_dir: Path to folder containing run data
        output: Output database path (default: src/shield_data/shield_data.db)
    """
    data_dir = Path(data_dir)
    output = _default_output() if output is None else Path(output)

    # Remove existing database
    if output.exists():
        output.unlink()

    conn = sqlite3.connect(output)
    cursor = conn.cursor()

    _create_schema(cursor)

    # Process each run folder
    run_folders = sorted(
        [d for d in data_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
    )

    for run_folder in run_folders:
        count = _insert_run(cursor, run_folder)
        print(f"✓ {run_folder.name}: {count} measurements")

    conn.commit()

    # Print summary
    run_count = cursor.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    meas_count = cursor.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]

    print(f"\n✓ Database created: {output}")
    print(f"  Runs: {run_count}")
    print(f"  Measurements: {meas_count:,}")
    print(f"  Size: {output.stat().st_size / 1024 / 1024:.2f} MB")

    conn.close()


def main() -> None:
    """CLI: full rebuild by default, or --add for incremental single-run insert."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--add",
        metavar="RUN_DIR",
        action="append",
        help="add/replace a single run folder instead of rebuilding (repeatable)",
    )
    parser.add_argument(
        "--data-dir", default="run_data", help="run data folder for full rebuild"
    )
    parser.add_argument(
        "--output", default=None, help="database path (default: package location)"
    )
    args = parser.parse_args()

    if args.add:
        for run_dir in args.add:
            add_run(run_dir, args.output)
    else:
        build_database(args.data_dir, args.output)


if __name__ == "__main__":
    main()
