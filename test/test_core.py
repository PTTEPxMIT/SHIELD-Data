from pathlib import Path

import pandas as pd
import pytest

from shield_data import catalogue, load, load_filtered, load_metadata


def test_catalogue_returns_dataframe():
    """catalogue() should return a pandas DataFrame."""
    result = catalogue()
    assert isinstance(result, pd.DataFrame)


def test_catalogue_has_expected_columns():
    """Catalogue contains the required columns in the expected order."""
    cat = catalogue()
    assert list(cat.columns) == [
        "run_id",
        "path",
        "run_type",
        "date",
        "furnace_setpoint",
        "material",
        "coating",
    ]


def test_load_valid_run_adds_run_id():
    """load(run_id) adds a 'run_id' column with the correct value."""
    cat = catalogue()
    pytest.skip("No runs available to test against") if cat.empty else None
    run_id = cat.iloc[0]["run_id"]
    df = load(run_id)
    assert "run_id" in df.columns
    assert (df["run_id"] == run_id).all()


def test_load_raises_for_missing_run():
    """load() raises FileNotFoundError when the run does not exist."""
    with pytest.raises(FileNotFoundError):
        load("non_existent_run_0000")


def test_load_metadata_contains_run_info():
    """load_metadata(run_id) returns dict with 'run_info' key."""
    cat = catalogue()
    pytest.skip("No runs available to test against") if cat.empty else None
    run_id = cat.iloc[0]["run_id"]
    meta = load_metadata(run_id)
    assert isinstance(meta, dict)
    assert "run_info" in meta


def test_load_filtered_filters_by_catalogue_values():
    """load_filtered(**filters) returns data matching catalogue-derived filters."""
    cat = catalogue()
    pytest.skip("No runs available to test against") if cat.empty else None
    # Use a value from the catalogue to construct a realistic filter
    row = cat.iloc[0]
    target_setpoint = row["furnace_setpoint"]

    df = load_filtered(furnace_setpoint=target_setpoint)
    # May be empty for some values, but if non-empty, all should match
    if not df.empty:
        # Verify only expected run_ids are included
        expected_ids = set(
            cat[cat["furnace_setpoint"].astype(str) == str(target_setpoint)][
                "run_id"
            ].tolist()
        )
        assert set(df["run_id"].unique()).issubset(expected_ids)


def test_load_filtered_raises_for_unknown_key():
    """Unknown filter keys should raise ValueError."""
    with pytest.raises(ValueError):
        load_filtered(not_a_real_column="value")


def test_catalogue_missing_file_raises(tmp_path: Path):
    """catalogue(data_dir) raises when runs_catalogue.csv is missing."""
    # Provide an empty directory as data_dir
    empty_dir = tmp_path / "data"
    empty_dir.mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        catalogue(empty_dir)
