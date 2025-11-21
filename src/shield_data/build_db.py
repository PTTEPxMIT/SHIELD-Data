"""Build SQLite database from run_data folder."""

import json
import sqlite3
from pathlib import Path

import pandas as pd


def build_database(data_dir: str | Path = "run_data", output: str | Path = None):
    """Build SQLite database from run data folder.

    Args:
        data_dir: Path to folder containing run data
        output: Output database path (default: src/shield_data/shield_data.db)
    """
    data_dir = Path(data_dir)
    if output is None:
        output = Path(__file__).parent / "shield_data.db"
    else:
        output = Path(output)

    # Remove existing database
    if output.exists():
        output.unlink()

    conn = sqlite3.connect(output)
    cursor = conn.cursor()

    # Create tables
    cursor.execute("""
        CREATE TABLE runs (
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
        CREATE TABLE measurements (
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

    # Index for fast queries
    cursor.execute("CREATE INDEX idx_run_id ON measurements(run_id)")
    cursor.execute("CREATE INDEX idx_date ON runs(date)")
    cursor.execute("CREATE INDEX idx_furnace_setpoint ON runs(furnace_setpoint)")

    # Process each run folder
    run_folders = sorted(
        [d for d in data_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
    )

    for run_folder in run_folders:
        run_id = run_folder.name
        metadata_file = run_folder / "run_metadata.json"
        data_file = run_folder / "pressure_gauge_data.csv"

        if not metadata_file.exists() or not data_file.exists():
            print(f"Skipping {run_id}: missing files")
            continue

        # Load metadata
        with open(metadata_file) as f:
            metadata = json.load(f)

        run_info = metadata.get("run_info", {})

        # Insert run metadata
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
                run_info.get("material"),
                run_info.get("coating"),
                json.dumps(metadata),
            ),
        )

        # Load and insert measurements
        df = pd.read_csv(data_file)

        # Prepare data for insertion
        measurements = []
        for _, row in df.iterrows():
            measurements.append(
                (
                    run_id,
                    row.get("RealTimestamp"),
                    row.get("WGM701_Voltage (V)"),
                    row.get("CVM211_Voltage (V)"),
                    row.get("Baratron626D_1KT_Voltage (V)"),
                    row.get("Baratron626D_1T_Voltage (V)"),
                )
            )

        cursor.executemany(
            """
            INSERT INTO measurements 
            (run_id, timestamp, WGM701_voltage, CVM211_voltage, 
             Baratron626D_1KT_voltage, Baratron626D_1T_voltage)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            measurements,
        )

        print(f"✓ {run_id}: {len(measurements)} measurements")

    conn.commit()

    # Print summary
    run_count = cursor.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    meas_count = cursor.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]

    print(f"\n✓ Database created: {output}")
    print(f"  Runs: {run_count}")
    print(f"  Measurements: {meas_count:,}")
    print(f"  Size: {output.stat().st_size / 1024 / 1024:.2f} MB")

    conn.close()


if __name__ == "__main__":
    build_database()
