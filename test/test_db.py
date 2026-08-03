"""Unit tests for db.py module.

Tests cover:
- Database connection
- Catalogue loading
- Run data loading
- Metadata loading
- Filtered data loading
- Error handling
"""

import json
import sqlite3

import pandas as pd
import pytest

from shield_data import build_db, db

# Fixtures


@pytest.fixture
def test_db(tmp_path):
    """Create a test database with sample data."""
    # Create test data directory
    data_dir = tmp_path / "run_data"
    data_dir.mkdir()

    # Create sample run 1
    run1_dir = data_dir / "25.10.06_run_1_10h41"
    run1_dir.mkdir()

    metadata1 = {
        "run_info": {
            "date": "2025-10-06",
            "start_time": "10:41:00",
            "run_type": "permeation_exp",
            "furnace_setpoint": 500,
            "material": "steel",
            "coating": "TiN",
        },
        "gauges": {"WGM701": "info"},
        "thermocouples": {"TC1": "info"},
    }

    with open(run1_dir / "run_metadata.json", "w") as f:
        json.dump(metadata1, f)

    df1 = pd.DataFrame(
        {
            "RealTimestamp": ["2025-10-06 10:41:00", "2025-10-06 10:41:01"],
            "WGM701_Voltage (V)": [1.1, 1.2],
            "CVM211_Voltage (V)": [2.1, 2.2],
            "Baratron626D_1KT_Voltage (V)": [3.1, 3.2],
            "Baratron626D_1T_Voltage (V)": [4.1, 4.2],
        }
    )
    df1.to_csv(run1_dir / "pressure_gauge_data.csv", index=False)

    # Create sample run 2 with different setpoint
    run2_dir = data_dir / "25.10.07_run_1_08h16"
    run2_dir.mkdir()

    metadata2 = {
        "run_info": {
            "date": "2025-10-07",
            "start_time": "08:16:00",
            "run_type": "permeation_exp",
            "furnace_setpoint": 400,
            "material": "aluminum",
            "coating": "None",
        },
        "gauges": {"WGM701": "info"},
        "thermocouples": {"TC1": "info"},
    }

    with open(run2_dir / "run_metadata.json", "w") as f:
        json.dump(metadata2, f)

    df2 = pd.DataFrame(
        {
            "RealTimestamp": [
                "2025-10-07 08:16:00",
                "2025-10-07 08:16:01",
                "2025-10-07 08:16:02",
            ],
            "WGM701_Voltage (V)": [5.1, 5.2, 5.3],
            "CVM211_Voltage (V)": [6.1, 6.2, 6.3],
            "Baratron626D_1KT_Voltage (V)": [7.1, 7.2, 7.3],
            "Baratron626D_1T_Voltage (V)": [8.1, 8.2, 8.3],
        }
    )
    df2.to_csv(run2_dir / "pressure_gauge_data.csv", index=False)

    # Build database
    db_path = tmp_path / "test.db"
    build_db.build_database(data_dir, db_path)

    # Temporarily override DB_PATH
    original_db_path = db.DB_PATH
    db.DB_PATH = db_path

    yield db_path

    # Restore original path
    db.DB_PATH = original_db_path


# Connection tests


def test_get_connection_returns_connection(test_db):
    """Test that _get_connection returns a sqlite3 Connection object."""
    conn = db._get_connection()

    assert isinstance(conn, sqlite3.Connection)
    conn.close()


def test_get_connection_has_row_factory(test_db):
    """Test that connection has Row factory set."""
    conn = db._get_connection()

    assert conn.row_factory == sqlite3.Row
    conn.close()


def test_get_connection_can_query_database(test_db):
    """Test that connection can execute queries."""
    with db._get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM runs")
        count = cursor.fetchone()[0]

    assert count == 2


# Catalogue tests


def test_catalogue_returns_dataframe(test_db):
    """Test that catalogue returns a pandas DataFrame."""
    result = db.catalogue()

    assert isinstance(result, pd.DataFrame)


def test_catalogue_has_correct_row_count(test_db):
    """Test that catalogue returns correct number of runs."""
    result = db.catalogue()

    assert len(result) == 2


@pytest.mark.parametrize(
    "column_name",
    [
        "run_id",
        "date",
        "start_time",
        "run_type",
        "furnace_setpoint",
        "material",
        "coating",
        "metadata",
    ],
)
def test_catalogue_has_required_column(test_db, column_name):
    """Test that catalogue DataFrame has each required column."""
    result = db.catalogue()

    assert column_name in result.columns


def test_catalogue_contains_expected_run_ids(test_db):
    """Test that catalogue contains the expected run IDs."""
    result = db.catalogue()

    run_ids = result["run_id"].tolist()
    assert "25.10.06_run_1_10h41" in run_ids
    assert "25.10.07_run_1_08h16" in run_ids


def test_catalogue_has_correct_furnace_setpoints(test_db):
    """Test that catalogue has correct furnace setpoint values."""
    result = db.catalogue()

    setpoints = result["furnace_setpoint"].tolist()
    assert 500 in setpoints
    assert 400 in setpoints


def test_catalogue_has_correct_dates(test_db):
    """Test that catalogue has correct date values."""
    result = db.catalogue()

    dates = result["date"].tolist()
    assert "2025-10-06" in dates
    assert "2025-10-07" in dates


# Load tests


def test_load_returns_dataframe(test_db):
    """Test that load returns a pandas DataFrame."""
    result = db.load("25.10.06_run_1_10h41")

    assert isinstance(result, pd.DataFrame)


def test_load_returns_correct_measurement_count(test_db):
    """Test that load returns correct number of measurements."""
    result = db.load("25.10.06_run_1_10h41")

    assert len(result) == 2


def test_load_different_run_has_different_count(test_db):
    """Test that different run returns different measurement count."""
    result = db.load("25.10.07_run_1_08h16")

    assert len(result) == 3


@pytest.mark.parametrize(
    "column_name",
    [
        "id",
        "run_id",
        "timestamp",
        "WGM701_voltage",
        "CVM211_voltage",
        "Baratron626D_1KT_voltage",
        "Baratron626D_1T_voltage",
    ],
)
def test_load_has_required_column(test_db, column_name):
    """Test that load DataFrame has each required column."""
    result = db.load("25.10.06_run_1_10h41")

    assert column_name in result.columns


def test_load_has_correct_run_id(test_db):
    """Test that load returns data for correct run_id."""
    result = db.load("25.10.06_run_1_10h41")

    assert all(result["run_id"] == "25.10.06_run_1_10h41")


def test_load_has_correct_voltage_values(test_db):
    """Test that load returns correct voltage values."""
    result = db.load("25.10.06_run_1_10h41")

    assert result["WGM701_voltage"].iloc[0] == 1.1
    assert result["WGM701_voltage"].iloc[1] == 1.2


def test_load_has_correct_timestamps(test_db):
    """Test that load returns correct timestamp values."""
    result = db.load("25.10.06_run_1_10h41")

    assert result["timestamp"].iloc[0] == "2025-10-06 10:41:00"
    assert result["timestamp"].iloc[1] == "2025-10-06 10:41:01"


def test_load_nonexistent_run_returns_empty_dataframe(test_db):
    """Test that load with nonexistent run_id returns empty DataFrame."""
    result = db.load("nonexistent_run")

    assert result.empty


# Load metadata tests


def test_load_metadata_returns_dict(test_db):
    """Test that load_metadata returns a dictionary."""
    result = db.load_metadata("25.10.06_run_1_10h41")

    assert isinstance(result, dict)


@pytest.mark.parametrize(
    "top_level_key",
    ["run_info", "gauges", "thermocouples"],
)
def test_load_metadata_has_required_top_level_key(test_db, top_level_key):
    """Test that load_metadata dict has each required top-level key."""
    result = db.load_metadata("25.10.06_run_1_10h41")

    assert top_level_key in result


def test_load_metadata_run_info_has_correct_date(test_db):
    """Test that run_info contains correct date."""
    result = db.load_metadata("25.10.06_run_1_10h41")

    assert result["run_info"]["date"] == "2025-10-06"


def test_load_metadata_run_info_has_correct_furnace_setpoint(test_db):
    """Test that run_info contains correct furnace setpoint."""
    result = db.load_metadata("25.10.06_run_1_10h41")

    assert result["run_info"]["furnace_setpoint"] == 500


def test_load_metadata_run_info_has_correct_material(test_db):
    """Test that run_info contains correct material."""
    result = db.load_metadata("25.10.06_run_1_10h41")

    assert result["run_info"]["material"] == "steel"


def test_load_metadata_different_run_has_different_values(test_db):
    """Test that different run has different metadata values."""
    result = db.load_metadata("25.10.07_run_1_08h16")

    assert result["run_info"]["date"] == "2025-10-07"
    assert result["run_info"]["furnace_setpoint"] == 400
    assert result["run_info"]["material"] == "aluminum"


# Load filtered tests


def test_load_filtered_with_furnace_setpoint_returns_dataframe(test_db):
    """Test that load_filtered returns a pandas DataFrame."""
    result = db.load_filtered(furnace_setpoint=500)

    assert isinstance(result, pd.DataFrame)


def test_load_filtered_by_furnace_setpoint_returns_correct_count(test_db):
    """Test that filtering by furnace_setpoint returns correct measurements."""
    result = db.load_filtered(furnace_setpoint=500)

    assert len(result) == 2  # Run 1 has 2 measurements


def test_load_filtered_by_different_setpoint_returns_different_count(test_db):
    """Test that filtering by different setpoint returns different count."""
    result = db.load_filtered(furnace_setpoint=400)

    assert len(result) == 3  # Run 2 has 3 measurements


def test_load_filtered_by_date_returns_correct_data(test_db):
    """Test that filtering by date returns correct run data."""
    result = db.load_filtered(date="2025-10-06")

    assert len(result) == 2
    assert all(result["run_id"] == "25.10.06_run_1_10h41")


def test_load_filtered_by_run_type_returns_all_runs(test_db):
    """Test that filtering by common run_type returns all runs."""
    result = db.load_filtered(run_type="permeation_exp")

    assert len(result) == 5  # 2 from run1 + 3 from run2


def test_load_filtered_by_material_returns_correct_run(test_db):
    """Test that filtering by material returns correct run."""
    result = db.load_filtered(material="steel")

    assert len(result) == 2
    assert all(result["run_id"] == "25.10.06_run_1_10h41")


def test_load_filtered_with_multiple_filters(test_db):
    """Test that multiple filters are applied correctly."""
    result = db.load_filtered(run_type="permeation_exp", furnace_setpoint=500)

    assert len(result) == 2
    assert all(result["run_id"] == "25.10.06_run_1_10h41")


def test_load_filtered_with_no_matches_returns_empty_dataframe(test_db):
    """Test that load_filtered with no matches returns empty DataFrame."""
    result = db.load_filtered(furnace_setpoint=999)

    assert result.empty


def test_load_filtered_invalid_column_raises_valueerror(test_db):
    """Test that filtering by invalid column raises ValueError."""
    with pytest.raises(ValueError, match="Unknown filter: invalid_column"):
        db.load_filtered(invalid_column="value")


def test_load_filtered_no_filters_returns_all_data(test_db):
    """Test that load_filtered with no filters returns all measurements."""
    result = db.load_filtered()

    assert len(result) == 5  # 2 from run1 + 3 from run2


# Integration tests


def test_catalogue_and_load_consistency(test_db):
    """Test that run_ids in catalogue can be loaded."""
    cat = db.catalogue()

    for run_id in cat["run_id"]:
        result = db.load(run_id)
        assert not result.empty
        assert all(result["run_id"] == run_id)


def test_catalogue_and_load_metadata_consistency(test_db):
    """Test that run_ids in catalogue have loadable metadata."""
    cat = db.catalogue()

    for run_id in cat["run_id"]:
        metadata = db.load_metadata(run_id)
        assert isinstance(metadata, dict)
        assert "run_info" in metadata


def test_load_filtered_matches_individual_loads(test_db):
    """Test that load_filtered result matches individual loads."""
    filtered = db.load_filtered(furnace_setpoint=500)
    individual = db.load("25.10.06_run_1_10h41")

    assert len(filtered) == len(individual)
    # Compare voltage values (excluding id column which may differ)
    assert filtered["WGM701_voltage"].tolist() == individual["WGM701_voltage"].tolist()


def test_metadata_matches_catalogue_values(test_db):
    """Test that metadata values match catalogue values."""
    cat = db.catalogue()
    run_id = "25.10.06_run_1_10h41"

    metadata = db.load_metadata(run_id)
    cat_row = cat[cat["run_id"] == run_id].iloc[0]

    assert metadata["run_info"]["date"] == cat_row["date"]
    assert metadata["run_info"]["furnace_setpoint"] == cat_row["furnace_setpoint"]
    assert metadata["run_info"]["material"] == cat_row["material"]


# Edge case tests


def test_catalogue_called_multiple_times_returns_same_data(test_db):
    """Test that catalogue can be called multiple times."""
    result1 = db.catalogue()
    result2 = db.catalogue()

    pd.testing.assert_frame_equal(result1, result2)


def test_load_called_multiple_times_returns_same_data(test_db):
    """Test that load can be called multiple times for same run."""
    result1 = db.load("25.10.06_run_1_10h41")
    result2 = db.load("25.10.06_run_1_10h41")

    pd.testing.assert_frame_equal(result1, result2)


def test_load_metadata_called_multiple_times_returns_same_data(test_db):
    """Test that load_metadata can be called multiple times."""
    result1 = db.load_metadata("25.10.06_run_1_10h41")
    result2 = db.load_metadata("25.10.06_run_1_10h41")

    assert result1 == result2


def test_load_filtered_with_string_value(test_db):
    """Test that load_filtered works with string filter values."""
    result = db.load_filtered(run_type="permeation_exp")

    assert not result.empty


def test_load_filtered_with_integer_value(test_db):
    """Test that load_filtered works with integer filter values."""
    result = db.load_filtered(furnace_setpoint=500)

    assert not result.empty


def test_load_with_case_sensitive_run_id(test_db):
    """Test that load is case-sensitive for run_id."""
    result = db.load("25.10.06_RUN_1_10H41")  # Wrong case

    assert result.empty


# Path resolution and cached-download tests


def _gz(data: bytes) -> bytes:
    import gzip

    return gzip.compress(data)


def test_get_db_path_prefers_env_var(tmp_path, monkeypatch):
    """Test that SHIELD_DATA_DB overrides all other resolution."""
    db_file = tmp_path / "pinned.db"
    db_file.touch()
    monkeypatch.setenv(db.DB_ENV_VAR, str(db_file))

    assert db.get_db_path() == db_file


def test_get_db_path_env_var_missing_file_raises(tmp_path, monkeypatch):
    """Test that a SHIELD_DATA_DB pointing at a missing file raises."""
    monkeypatch.setenv(db.DB_ENV_VAR, str(tmp_path / "nope.db"))

    with pytest.raises(FileNotFoundError):
        db.get_db_path()


def test_get_db_path_uses_local_checkout_db(tmp_path, monkeypatch):
    """Test that a database next to the source wins over the cache."""
    monkeypatch.delenv(db.DB_ENV_VAR, raising=False)
    local = tmp_path / "shield_data.db"
    local.touch()
    monkeypatch.setattr(db, "_LOCAL_DB", local)

    assert db.get_db_path() == local


def test_get_db_path_falls_back_to_cache(tmp_path, monkeypatch):
    """Test that an existing cached download is used without network."""
    monkeypatch.delenv(db.DB_ENV_VAR, raising=False)
    monkeypatch.setattr(db, "_LOCAL_DB", tmp_path / "absent.db")
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "shield_data.db").touch()
    monkeypatch.setattr(db, "_cache_dir", lambda: cache)

    assert db.get_db_path() == cache / "shield_data.db"


def test_update_database_downloads_verifies_and_caches(tmp_path, monkeypatch):
    """Test that update_database fetches, checksum-verifies, and caches."""
    import hashlib

    raw = b"sqlite pretend bytes"
    manifest = {"sha256": hashlib.sha256(raw).hexdigest(), "runs": 3}
    responses = {
        f"{db.DATA_RELEASE_URL}/manifest.json": json.dumps(manifest).encode(),
        f"{db.DATA_RELEASE_URL}/shield_data.db.gz": _gz(raw),
    }
    cache = tmp_path / "cache"
    monkeypatch.setattr(db, "_cache_dir", lambda: cache)
    monkeypatch.setattr(db, "_fetch", lambda url: responses[url])

    result = db.update_database()

    assert result == cache / "shield_data.db"
    assert result.read_bytes() == raw
    assert json.loads((cache / "manifest.json").read_text()) == manifest


def test_update_database_skips_download_when_cache_current(tmp_path, monkeypatch):
    """Test that a current cache short-circuits before downloading the db."""
    import hashlib

    raw = b"sqlite pretend bytes"
    manifest = {"sha256": hashlib.sha256(raw).hexdigest()}
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "shield_data.db").write_bytes(raw)
    (cache / "manifest.json").write_text(json.dumps(manifest))

    def fetch(url):
        if url.endswith("manifest.json"):
            return json.dumps(manifest).encode()
        raise AssertionError("database should not be re-downloaded")

    monkeypatch.setattr(db, "_cache_dir", lambda: cache)
    monkeypatch.setattr(db, "_fetch", fetch)

    assert db.update_database() == cache / "shield_data.db"


def test_update_database_checksum_mismatch_raises(tmp_path, monkeypatch):
    """Test that a corrupted download is rejected and the cache untouched."""
    responses = {
        f"{db.DATA_RELEASE_URL}/manifest.json": json.dumps(
            {"sha256": "0" * 64}
        ).encode(),
        f"{db.DATA_RELEASE_URL}/shield_data.db.gz": _gz(b"tampered"),
    }
    cache = tmp_path / "cache"
    monkeypatch.setattr(db, "_cache_dir", lambda: cache)
    monkeypatch.setattr(db, "_fetch", lambda url: responses[url])

    with pytest.raises(RuntimeError, match="checksum mismatch"):
        db.update_database()
    assert not (cache / "shield_data.db").exists()
