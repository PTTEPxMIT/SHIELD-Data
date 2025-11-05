import pandas as pd

from shield_data import catalogue, load


def test_catalogue_returns_dataframe():
    """Catalogue function should return a pandas DataFrame."""
    result = catalogue()
    assert isinstance(result, pd.DataFrame)


def test_catalogue_contains_expected_columns():
    """Catalogue DataFrame should contain all required columns."""
    cat = catalogue()
    expected_columns = [
        "run_id",
        "path",
        "run_type",
        "date",
        "furnace_setpoint",
        "material",
        "coating",
    ]
    assert list(cat.columns) == expected_columns


def test_load_adds_run_id_column():
    """Load function should add a run_id column to the data."""
    cat = catalogue()
    if not cat.empty:
        run_id = cat.iloc[0]["run_id"]
        df = load(run_id)
        assert "run_id" in df.columns
        assert (df["run_id"] == run_id).all()
