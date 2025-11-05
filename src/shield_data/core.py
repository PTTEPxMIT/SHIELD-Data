import json
from pathlib import Path

import pandas as pd


def catalogue(data_dir: str | Path = "run_data") -> pd.DataFrame:
    """Load the catalogue of all experimental runs.

    Args:
        data_dir: Path to the data directory containing runs_catalogue.csv

    Returns:
        DataFrame with columns: run_id, path, run_type, date,
        furnace_setpoint, material, coating
    """
    data_dir = Path(data_dir)
    catalogue_path = data_dir / "runs_catalogue.csv"

    if not catalogue_path.exists():
        raise FileNotFoundError(f"Catalogue not found at {catalogue_path}")

    return pd.read_csv(catalogue_path)


def load(run_id: str, data_dir: str | Path = "run_data") -> pd.DataFrame:
    """Load pressure gauge data for a specific run.

    Args:
        run_id: The run ID (folder name) to load
        data_dir: Path to the data directory

    Returns:
        DataFrame containing the pressure gauge data with a 'run_id' column added
    """
    data_dir = Path(data_dir)
    run_path = data_dir / run_id / "pressure_gauge_data.csv"

    if not run_path.exists():
        raise FileNotFoundError(f"Data file not found at {run_path}")

    df = pd.read_csv(run_path)
    df["run_id"] = run_id
    return df


def load_metadata(run_id: str, data_dir: str | Path = "run_data") -> dict:
    """Load metadata for a specific run.

    Args:
        run_id: The run ID (folder name) to load
        data_dir: Path to the data directory

    Returns:
        Dictionary containing the run metadata
    """
    data_dir = Path(data_dir)
    metadata_path = data_dir / run_id / "run_metadata.json"

    if not metadata_path.exists():
        raise FileNotFoundError(f"Metadata file not found at {metadata_path}")

    with open(metadata_path) as f:
        return json.load(f)


def load_filtered(**filters) -> pd.DataFrame:
    """Load data for runs matching filter criteria.

    Filter on any column in the catalogue (run_type, date, furnace_setpoint, etc.)
    Multiple filters are combined with AND logic.

    Args:
        **filters: Keyword arguments for filtering (e.g., run_type="permeation_exp",
                   furnace_setpoint=500)

    Returns:
        Combined DataFrame of all matching runs with run_id column

    Example:
        >>> # Load all runs at 500K
        >>> df = load_filtered(furnace_setpoint=500)
        >>>
        >>> # Load permeation experiments from a specific date
        >>> df = load_filtered(run_type="permeation_exp", date="2025-10-06")
    """
    cat = catalogue()

    # Apply filters
    for key, value in filters.items():
        if key not in cat.columns:
            raise ValueError(f"Unknown filter key: {key}")
        # Convert to string for comparison to handle mixed types
        cat = cat[cat[key].astype(str) == str(value)]

    if cat.empty:
        return pd.DataFrame()

    # Load and combine all matching runs
    frames = [load(row["run_id"]) for _, row in cat.iterrows()]
    return pd.concat(frames, ignore_index=True)
