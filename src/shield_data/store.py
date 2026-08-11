"""Run-folder storage layer: Parquet measurements and the run catalogue.

Each run folder under ``run_data/`` stores its measurements as a single
zstd-compressed Parquet file (``measurements.parquet``) alongside
``run_metadata.json``. Parquet files are self-describing: a run keeps exactly
the columns the rig recorded (four gauge voltages, optionally temperatures,
or whatever future instrumentation adds), so new channels never require a
schema migration. Legacy runs that still hold a ``pressure_gauge_data.csv``
are read transparently.

This module provides:

- :func:`read_measurements` — read a run folder in either format, with
  ``RealTimestamp`` parsed to datetimes.
- :func:`convert_run` — convert a legacy CSV run to Parquet, verifying an
  exact round-trip (row counts, column names, bit-identical values) before
  optionally deleting the CSV.
- :func:`build_catalogue` — scan ``run_data/`` into the catalogue: one row
  per run with normalised metadata fields, the list of recorded channels,
  and the sha256 of the data file (used to verify per-run downloads).

CLI (used by CI and for the one-off backfill)::

    python -m shield_data.store convert run_data --delete-csv
    python -m shield_data.store catalogue run_data --output catalogue.parquet
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

MEASUREMENTS_FILENAME = "measurements.parquet"
LEGACY_CSV_FILENAME = "pressure_gauge_data.csv"
CATALOGUE_FILENAME = "catalogue.parquet"
METADATA_FILENAME = "run_metadata.json"
TIMESTAMP_COLUMN = "RealTimestamp"

PARQUET_COMPRESSION = "zstd"
PARQUET_COMPRESSION_LEVEL = 9


def data_file(run_dir: str | Path) -> Path:
    """Return the run's data file (Parquet preferred, legacy CSV fallback).

    Args:
        run_dir: Run folder (run_data/YY.MM.DD_run_X_HHhMM)

    Raises:
        FileNotFoundError: If the folder holds neither format.
    """
    run_dir = Path(run_dir)
    parquet = run_dir / MEASUREMENTS_FILENAME
    if parquet.exists():
        return parquet
    csv = run_dir / LEGACY_CSV_FILENAME
    if csv.exists():
        return csv
    raise FileNotFoundError(
        f"{run_dir} contains neither {MEASUREMENTS_FILENAME} nor {LEGACY_CSV_FILENAME}"
    )


def _parse_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    if TIMESTAMP_COLUMN in df.columns and not pd.api.types.is_datetime64_any_dtype(
        df[TIMESTAMP_COLUMN]
    ):
        df[TIMESTAMP_COLUMN] = pd.to_datetime(df[TIMESTAMP_COLUMN], format="mixed")
    return df


def read_measurements(run_dir: str | Path) -> pd.DataFrame:
    """Read a run's measurements from either storage format.

    Args:
        run_dir: Run folder containing measurements.parquet or the legacy
            pressure_gauge_data.csv

    Returns:
        DataFrame with RealTimestamp as datetime64 and every channel the rig
        recorded (voltages in V or mV, temperatures in C — see column names)
    """
    path = data_file(run_dir)
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return _parse_timestamps(pd.read_csv(path))


def channels(df: pd.DataFrame) -> list[str]:
    """Names of the recorded data channels (every column except the timestamp)."""
    return [c for c in df.columns if c != TIMESTAMP_COLUMN]


def sha256_of(path: str | Path) -> str:
    """sha256 hex digest of a file's bytes."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_round_trip(original: pd.DataFrame, parquet_path: Path) -> list[str]:
    """Compare a written Parquet file against the DataFrame it came from.

    Returns a list of problems; empty means the round-trip is exact.
    """
    problems = []
    back = pd.read_parquet(parquet_path)
    if len(back) != len(original):
        problems.append(f"row count {len(back)} != {len(original)}")
    if list(back.columns) != list(original.columns):
        problems.append(f"columns {list(back.columns)} != {list(original.columns)}")
        return problems
    for col in original.columns:
        a, b = original[col], back[col]
        if col == TIMESTAMP_COLUMN:
            if not a.equals(b.astype(a.dtype)):
                problems.append(f"timestamp mismatch in {col}")
        elif not a.equals(b):
            problems.append(f"value mismatch in {col}")
    return problems


def convert_run(run_dir: str | Path, delete_csv: bool = False) -> Path:
    """Convert one legacy CSV run folder to Parquet, verifying exactness.

    The CSV is read, timestamps parsed, and the result written as
    zstd-compressed Parquet. The written file is read back and checked for an
    exact round-trip (same rows, same columns, bit-identical float64 values)
    before the CSV is optionally deleted — a failed check raises and leaves
    the CSV in place.

    Args:
        run_dir: Run folder containing pressure_gauge_data.csv
        delete_csv: Remove the CSV after a verified conversion

    Returns:
        Path to the written measurements.parquet

    Raises:
        RuntimeError: If the round-trip verification fails.
    """
    run_dir = Path(run_dir)
    csv_path = run_dir / LEGACY_CSV_FILENAME
    df = _parse_timestamps(pd.read_csv(csv_path))

    parquet_path = run_dir / MEASUREMENTS_FILENAME
    df.to_parquet(
        parquet_path,
        index=False,
        compression=PARQUET_COMPRESSION,
        compression_level=PARQUET_COMPRESSION_LEVEL,
    )

    problems = _verify_round_trip(df, parquet_path)
    if problems:
        parquet_path.unlink(missing_ok=True)
        raise RuntimeError(f"{run_dir.name}: round-trip failed: {'; '.join(problems)}")

    if delete_csv:
        csv_path.unlink()
    return parquet_path


def _normalised_run_fields(metadata: dict) -> dict:
    run_info = metadata.get("run_info", {})
    return {
        "date": run_info.get("date"),
        "start_time": run_info.get("start_time"),
        "end_time": run_info.get("end_time"),
        "run_type": run_info.get("run_type"),
        "furnace_setpoint": run_info.get("furnace_setpoint"),
        # v1.0 metadata calls this "material", v1.3 "sample_material"
        "material": run_info.get("material", run_info.get("sample_material")),
        "coating": run_info.get("coating"),
    }


def build_catalogue(
    data_dir: str | Path, output: str | Path | None = None
) -> pd.DataFrame:
    """Build the run catalogue from a run_data directory.

    One row per run folder: run_id, normalised metadata fields (material
    falls back to v1.3's sample_material), the list of recorded channels,
    measurement count, and the data file's name, size, and sha256 (used to
    verify per-run downloads). The full run_metadata.json is carried in the
    ``metadata`` column so ``load_metadata`` needs no further download.

    Args:
        data_dir: Path to the run_data folder
        output: Optional path to also write the catalogue as Parquet

    Returns:
        The catalogue as a DataFrame, sorted by run_id
    """
    data_dir = Path(data_dir)
    rows = []
    for run_dir in sorted(data_dir.iterdir()):
        if not run_dir.is_dir() or run_dir.name.startswith("."):
            continue
        with open(run_dir / METADATA_FILENAME) as f:
            metadata = json.load(f)
        df = read_measurements(run_dir)
        path = data_file(run_dir)
        rows.append(
            {
                "run_id": run_dir.name,
                **_normalised_run_fields(metadata),
                "channels": channels(df),
                "n_measurements": len(df),
                "data_file": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_of(path),
                "metadata": json.dumps(metadata),
            }
        )

    cat = pd.DataFrame(rows)
    if output is not None:
        cat.to_parquet(Path(output), index=False, compression=PARQUET_COMPRESSION)
    return cat


def main(argv: list[str] | None = None) -> int:
    """CLI: convert legacy CSV runs to Parquet, or build the catalogue."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_convert = sub.add_parser("convert", help="convert CSV run folders to Parquet")
    p_convert.add_argument("data_dir", help="run_data directory (or one run folder)")
    p_convert.add_argument(
        "--delete-csv",
        action="store_true",
        help="remove each CSV after its conversion is verified",
    )

    p_cat = sub.add_parser("catalogue", help="build the run catalogue")
    p_cat.add_argument("data_dir", help="run_data directory")
    p_cat.add_argument("--output", default=CATALOGUE_FILENAME, help="output path")

    args = parser.parse_args(argv)

    if args.command == "convert":
        root = Path(args.data_dir)
        if (root / LEGACY_CSV_FILENAME).exists():
            run_dirs = [root]
        else:
            run_dirs = sorted(
                d
                for d in root.iterdir()
                if d.is_dir()
                and not d.name.startswith(".")
                and (d / LEGACY_CSV_FILENAME).exists()
            )
        for run_dir in run_dirs:
            csv_size = (run_dir / LEGACY_CSV_FILENAME).stat().st_size
            parquet_path = convert_run(run_dir, delete_csv=args.delete_csv)
            print(
                f"✓ {run_dir.name}: {csv_size / 1e6:.1f} MB csv -> "
                f"{parquet_path.stat().st_size / 1e6:.1f} MB parquet"
            )
        print(f"Converted {len(run_dirs)} run(s)")
    else:
        cat = build_catalogue(args.data_dir, output=args.output)
        print(f"✓ catalogue: {len(cat)} runs -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
