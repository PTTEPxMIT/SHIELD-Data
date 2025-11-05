from pathlib import Path

import pandas as pd
import pytest

from shield_data import catalogue, load, load_filtered, load_metadata


def test_catalogue_returns_dataframe():
    """Test that catalogue() returns a pandas DataFrame.

    The catalogue function should always return a DataFrame, even if empty.
    This ensures compatibility with pandas operations and downstream analysis.
    """
    result = catalogue()
    assert isinstance(result, pd.DataFrame)


@pytest.mark.parametrize(
    "column_name",
    ["run_id", "path", "run_type", "date", "furnace_setpoint", "material", "coating"],
)
def test_catalogue_has_column(column_name):
    """Test that catalogue contains each required column.

    The catalogue must have all expected columns to ensure downstream code
    can safely access metadata fields without KeyErrors. Each column is tested
    individually so failures clearly indicate which column is missing.
    """
    cat = catalogue()
    assert column_name in cat.columns


def test_catalogue_column_order():
    """Test that catalogue columns are in the expected order.

    Column order matters for display, CSV output, and code that accesses
    columns by position. This ensures consistency with the schema defined
    in build_catalogue.py.
    """
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


def test_load_adds_run_id_column():
    """Test that load() adds a 'run_id' column to the data.

    The run_id column is crucial for tracking which run each data point
    belongs to, especially when combining multiple runs with load_filtered().
    This verifies the column is added to the returned DataFrame.
    """
    cat = catalogue()
    if cat.empty:
        pytest.skip("No runs available to test against")
    run_id = cat.iloc[0]["run_id"]
    df = load(run_id)
    assert "run_id" in df.columns


def test_load_run_id_column_has_correct_value():
    """Test that load() populates run_id column with the correct value.

    Every row in the loaded data should have the run_id set to the requested
    run identifier. This ensures data provenance is maintained when runs are
    concatenated or analyzed together.
    """
    cat = catalogue()
    if cat.empty:
        pytest.skip("No runs available to test against")
    run_id = cat.iloc[0]["run_id"]
    df = load(run_id)
    assert (df["run_id"] == run_id).all()


def test_load_raises_for_missing_run():
    """Test that load() raises FileNotFoundError for non-existent runs.

    Attempting to load a run that doesn't exist should fail fast with a clear
    error rather than returning empty data or failing silently. This helps
    users quickly identify typos or missing data.
    """
    with pytest.raises(FileNotFoundError):
        load("non_existent_run_0000")


def test_load_metadata_returns_dict():
    """Test that load_metadata() returns a dictionary.

    Metadata should be returned as a dict to allow easy access to nested
    fields like run_info and support JSON-like data structures. This verifies
    the return type is correct.
    """
    cat = catalogue()
    if cat.empty:
        pytest.skip("No runs available to test against")
    run_id = cat.iloc[0]["run_id"]
    meta = load_metadata(run_id)
    assert isinstance(meta, dict)


def test_load_metadata_contains_run_info():
    """Test that metadata contains the 'run_info' key.

    The run_info field is the primary metadata structure containing run
    parameters like run_type, date, setpoint, etc. This verifies the expected
    schema is present in loaded metadata.
    """
    cat = catalogue()
    if cat.empty:
        pytest.skip("No runs available to test against")
    run_id = cat.iloc[0]["run_id"]
    meta = load_metadata(run_id)
    assert "run_info" in meta


def test_load_filtered_returns_matching_runs():
    """Test that load_filtered() only returns runs matching the filter criteria.

    When filtering by catalogue fields (e.g., furnace_setpoint), only runs
    with matching values should be included. This verifies the filtering logic
    correctly restricts the returned data to the requested subset.
    """
    cat = catalogue()
    if cat.empty:
        pytest.skip("No runs available to test against")
    row = cat.iloc[0]
    target_setpoint = row["furnace_setpoint"]

    df = load_filtered(furnace_setpoint=target_setpoint)
    if not df.empty:
        expected_ids = set(
            cat[cat["furnace_setpoint"].astype(str) == str(target_setpoint)][
                "run_id"
            ].tolist()
        )
        assert set(df["run_id"].unique()).issubset(expected_ids)


def test_load_filtered_raises_for_unknown_key():
    """Test that load_filtered() raises ValueError for invalid filter keys.

    Filtering by non-existent catalogue columns should fail immediately with
    a clear error message. This prevents silent failures and helps users
    identify typos in filter keys.
    """
    with pytest.raises(ValueError):
        load_filtered(not_a_real_column="value")


def test_catalogue_missing_file_raises(tmp_path: Path):
    """Test that catalogue() raises FileNotFoundError when CSV is missing.

    If the runs_catalogue.csv file doesn't exist, catalogue() should fail
    with a clear error rather than creating an empty DataFrame. This helps
    users identify when the catalogue needs to be built.
    """
    empty_dir = tmp_path / "data"
    empty_dir.mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        catalogue(empty_dir)


def test_load_metadata_raises_for_missing_file():
    """Test that load_metadata() raises FileNotFoundError for missing metadata.

    If run_metadata.json doesn't exist for a run, the function should fail
    clearly rather than returning empty data. This helps identify incomplete
    run data or incorrect run IDs.
    """
    with pytest.raises(FileNotFoundError):
        load_metadata("non_existent_run_0000")


def test_load_filtered_returns_dataframe_for_no_matches():
    """Test that load_filtered() returns a DataFrame even with no matches.

    When no runs match the filter criteria, the function should still return
    a DataFrame (just empty) rather than None or raising an error. This allows
    consistent handling in analysis code.
    """
    df = load_filtered(furnace_setpoint="99999999")
    assert isinstance(df, pd.DataFrame)


def test_load_filtered_returns_empty_for_no_matches():
    """Test that load_filtered() returns an empty DataFrame when no matches.

    With filter criteria that match no runs, the returned DataFrame should
    have zero rows. This verifies the filtering correctly handles the
    no-match case without errors.
    """
    df = load_filtered(furnace_setpoint="99999999")
    assert df.empty
