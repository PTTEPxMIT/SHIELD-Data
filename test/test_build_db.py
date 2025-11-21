import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from shield_data.build_db import build_database

# Fixtures


@pytest.fixture
def temp_data_dir(tmp_path):
    """Create a temporary data directory with sample run data."""
    data_dir = tmp_path / "run_data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def sample_metadata():
    """Return sample metadata dictionary."""
    return {
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


@pytest.fixture
def sample_csv_data():
    """Return sample CSV data as DataFrame."""
    return pd.DataFrame(
        {
            "RealTimestamp": ["2025-10-06 10:41:00", "2025-10-06 10:41:01"],
            "WGM701_Voltage (V)": [1.23, 1.24],
            "CVM211_Voltage (V)": [2.34, 2.35],
            "Baratron626D_1KT_Voltage (V)": [3.45, 3.46],
            "Baratron626D_1T_Voltage (V)": [4.56, 4.57],
        }
    )


@pytest.fixture
def single_run_dir(temp_data_dir, sample_metadata, sample_csv_data):
    """Create a single run directory with metadata and CSV."""
    run_dir = temp_data_dir / "25.10.06_run_1_10h41"
    run_dir.mkdir()

    # Write metadata
    with open(run_dir / "run_metadata.json", "w") as f:
        json.dump(sample_metadata, f)

    # Write CSV
    sample_csv_data.to_csv(run_dir / "pressure_gauge_data.csv", index=False)

    return temp_data_dir


# Database creation tests


def test_database_file_is_created(single_run_dir, tmp_path):
    """Test that database file is created at specified output path."""
    output = tmp_path / "test.db"

    build_database(single_run_dir, output)

    assert output.exists()


def test_database_file_is_sqlite_format(single_run_dir, tmp_path):
    """Test that created file is a valid SQLite database."""
    output = tmp_path / "test.db"

    build_database(single_run_dir, output)

    # Should be able to connect without error
    with sqlite3.connect(output):
        pass  # Connection successful, nothing more needed


def test_existing_database_is_replaced(single_run_dir, tmp_path):
    """Test that existing database file is replaced when building."""
    output = tmp_path / "test.db"

    # Create initial database
    build_database(single_run_dir, output)
    initial_size = output.stat().st_size

    # Rebuild database
    build_database(single_run_dir, output)
    new_size = output.stat().st_size

    # Size should be same (replaced, not appended)
    assert new_size == initial_size


def test_default_output_path_is_used(single_run_dir, monkeypatch):
    """Test that default output path is src/shield_data/shield_data.db."""
    # Mock __file__ location
    fake_module_path = single_run_dir / "build_db.py"
    fake_module_path.touch()
    monkeypatch.setattr("shield_data.build_db.__file__", str(fake_module_path))

    build_database(single_run_dir)

    expected_path = single_run_dir / "shield_data.db"
    assert expected_path.exists()


# Schema tests


def test_runs_table_exists(single_run_dir, tmp_path):
    """Test that runs table is created in database."""
    output = tmp_path / "test.db"
    build_database(single_run_dir, output)

    with sqlite3.connect(output) as conn:
        cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='runs'")
    result = cursor.fetchone()
    assert result is not None


def test_measurements_table_exists(single_run_dir, tmp_path):
    """Test that measurements table is created in database."""
    output = tmp_path / "test.db"
    build_database(single_run_dir, output)

    with sqlite3.connect(output) as conn:
        cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='measurements'"
    )
    result = cursor.fetchone()
    assert result is not None


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
def test_runs_table_has_required_column(single_run_dir, tmp_path, column_name):
    """Test that runs table has each required column."""
    output = tmp_path / "test.db"
    build_database(single_run_dir, output)

    with sqlite3.connect(output) as conn:
        cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(runs)")
    columns = [row[1] for row in cursor.fetchall()]
    assert column_name in columns


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
def test_measurements_table_has_required_column(single_run_dir, tmp_path, column_name):
    """Test that measurements table has each required column."""
    output = tmp_path / "test.db"
    build_database(single_run_dir, output)

    with sqlite3.connect(output) as conn:
        cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(measurements)")
    columns = [row[1] for row in cursor.fetchall()]
    assert column_name in columns


def test_run_id_is_primary_key(single_run_dir, tmp_path):
    """Test that run_id is set as primary key in runs table."""
    output = tmp_path / "test.db"
    build_database(single_run_dir, output)

    with sqlite3.connect(output) as conn:
        cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(runs)")
    columns = cursor.fetchall()
    conn.close()

    run_id_col = next(col for col in columns if col[1] == "run_id")
    is_primary_key = run_id_col[5] == 1  # pk column is index 5

    assert is_primary_key


def test_measurements_id_is_autoincrement(single_run_dir, tmp_path):
    """Test that id column in measurements is autoincrement primary key."""
    output = tmp_path / "test.db"
    build_database(single_run_dir, output)

    with sqlite3.connect(output) as conn:
        cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(measurements)")
    columns = cursor.fetchall()
    conn.close()

    id_col = next(col for col in columns if col[1] == "id")
    is_primary_key = id_col[5] == 1

    assert is_primary_key


# Index tests


@pytest.mark.parametrize(
    "index_name",
    ["idx_run_id", "idx_date", "idx_furnace_setpoint"],
)
def test_index_is_created(single_run_dir, tmp_path, index_name):
    """Test that each required index is created."""
    output = tmp_path / "test.db"
    build_database(single_run_dir, output)

    with sqlite3.connect(output) as conn:
        cursor = conn.cursor()
    cursor.execute(
        f"SELECT name FROM sqlite_master WHERE type='index' AND name='{index_name}'"
    )
    result = cursor.fetchone()
    assert result is not None


# Data insertion tests


def test_single_run_is_inserted(single_run_dir, tmp_path):
    """Test that a single run is inserted into runs table."""
    output = tmp_path / "test.db"
    build_database(single_run_dir, output)

    with sqlite3.connect(output) as conn:
        cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM runs")
    count = cursor.fetchone()[0]
    assert count == 1


def test_run_id_is_inserted_correctly(single_run_dir, tmp_path):
    """Test that run_id from folder name is inserted correctly."""
    output = tmp_path / "test.db"
    build_database(single_run_dir, output)

    with sqlite3.connect(output) as conn:
        cursor = conn.cursor()
    cursor.execute("SELECT run_id FROM runs")
    run_id = cursor.fetchone()[0]
    assert run_id == "25.10.06_run_1_10h41"


def test_date_is_inserted_from_metadata(single_run_dir, tmp_path):
    """Test that date from run_info is inserted correctly."""
    output = tmp_path / "test.db"
    build_database(single_run_dir, output)

    with sqlite3.connect(output) as conn:
        cursor = conn.cursor()
    cursor.execute("SELECT date FROM runs")
    date = cursor.fetchone()[0]
    assert date == "2025-10-06"


def test_furnace_setpoint_is_inserted_as_integer(single_run_dir, tmp_path):
    """Test that furnace_setpoint is stored as integer."""
    output = tmp_path / "test.db"
    build_database(single_run_dir, output)

    with sqlite3.connect(output) as conn:
        cursor = conn.cursor()
    cursor.execute("SELECT furnace_setpoint FROM runs")
    setpoint = cursor.fetchone()[0]
    assert setpoint == 500
    assert isinstance(setpoint, int)


def test_full_metadata_json_is_stored(single_run_dir, tmp_path, sample_metadata):
    """Test that complete metadata JSON is stored in metadata column."""
    output = tmp_path / "test.db"
    build_database(single_run_dir, output)

    with sqlite3.connect(output) as conn:
        cursor = conn.cursor()
    cursor.execute("SELECT metadata FROM runs")
    metadata_str = cursor.fetchone()[0]
    conn.close()

    stored_metadata = json.loads(metadata_str)

    assert stored_metadata == sample_metadata


def test_measurements_are_inserted(single_run_dir, tmp_path):
    """Test that measurements are inserted into measurements table."""
    output = tmp_path / "test.db"
    build_database(single_run_dir, output)

    with sqlite3.connect(output) as conn:
        cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM measurements")
    count = cursor.fetchone()[0]
    assert count == 2


def test_measurement_timestamps_are_inserted(single_run_dir, tmp_path):
    """Test that RealTimestamp column is mapped to timestamp."""
    output = tmp_path / "test.db"
    build_database(single_run_dir, output)

    with sqlite3.connect(output) as conn:
        cursor = conn.cursor()
    cursor.execute("SELECT timestamp FROM measurements ORDER BY id LIMIT 1")
    timestamp = cursor.fetchone()[0]
    assert timestamp == "2025-10-06 10:41:00"


def test_measurement_voltages_are_inserted(single_run_dir, tmp_path):
    """Test that voltage columns are inserted with correct values."""
    output = tmp_path / "test.db"
    build_database(single_run_dir, output)

    with sqlite3.connect(output) as conn:
        cursor = conn.cursor()
    cursor.execute(
        """
        SELECT WGM701_voltage, CVM211_voltage,
               Baratron626D_1KT_voltage, Baratron626D_1T_voltage
        FROM measurements ORDER BY id LIMIT 1
    """
    )
    voltages = cursor.fetchone()
    assert voltages == (1.23, 2.34, 3.45, 4.56)


def test_measurement_run_id_foreign_key(single_run_dir, tmp_path):
    """Test that measurements are linked to runs via run_id."""
    output = tmp_path / "test.db"
    build_database(single_run_dir, output)

    with sqlite3.connect(output) as conn:
        cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT run_id FROM measurements")
    meas_run_id = cursor.fetchone()[0]
    cursor.execute("SELECT run_id FROM runs")
    runs_run_id = cursor.fetchone()[0]
    assert meas_run_id == runs_run_id


# Multiple runs tests


def test_multiple_runs_are_processed(
    temp_data_dir, sample_metadata, sample_csv_data, tmp_path
):
    """Test that multiple run folders are all processed."""
    # Create two run folders
    for run_name in ["25.10.06_run_1_10h41", "25.10.07_run_1_08h16"]:
        run_dir = temp_data_dir / run_name
        run_dir.mkdir()
        with open(run_dir / "run_metadata.json", "w") as f:
            json.dump(sample_metadata, f)
        sample_csv_data.to_csv(run_dir / "pressure_gauge_data.csv", index=False)

    output = tmp_path / "test.db"
    build_database(temp_data_dir, output)

    with sqlite3.connect(output) as conn:
        cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM runs")
    count = cursor.fetchone()[0]
    assert count == 2


def test_runs_are_processed_in_sorted_order(
    temp_data_dir, sample_metadata, sample_csv_data, tmp_path
):
    """Test that run folders are processed in alphabetically sorted order."""
    # Create runs in non-alphabetical order
    run_names = ["25.10.08_run_1_08h34", "25.10.06_run_1_10h41", "25.10.07_run_1_08h16"]
    for run_name in run_names:
        run_dir = temp_data_dir / run_name
        run_dir.mkdir()
        with open(run_dir / "run_metadata.json", "w") as f:
            json.dump(sample_metadata, f)
        sample_csv_data.to_csv(run_dir / "pressure_gauge_data.csv", index=False)

    output = tmp_path / "test.db"
    build_database(temp_data_dir, output)

    with sqlite3.connect(output) as conn:
        cursor = conn.cursor()
    cursor.execute("SELECT run_id FROM runs ORDER BY rowid")
    run_ids = [row[0] for row in cursor.fetchall()]
    assert run_ids == sorted(run_names)


def test_hidden_directories_are_skipped(
    temp_data_dir, sample_metadata, sample_csv_data, tmp_path
):
    """Test that directories starting with dot are skipped."""
    # Create normal run
    run_dir = temp_data_dir / "25.10.06_run_1_10h41"
    run_dir.mkdir()
    with open(run_dir / "run_metadata.json", "w") as f:
        json.dump(sample_metadata, f)
    sample_csv_data.to_csv(run_dir / "pressure_gauge_data.csv", index=False)

    # Create hidden directory
    hidden_dir = temp_data_dir / ".hidden_run"
    hidden_dir.mkdir()
    with open(hidden_dir / "run_metadata.json", "w") as f:
        json.dump(sample_metadata, f)
    sample_csv_data.to_csv(hidden_dir / "pressure_gauge_data.csv", index=False)

    output = tmp_path / "test.db"
    build_database(temp_data_dir, output)

    with sqlite3.connect(output) as conn:
        cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM runs")
    count = cursor.fetchone()[0]
    assert count == 1


# Path handling tests


def test_string_path_is_accepted_for_data_dir(single_run_dir, tmp_path):
    """Test that data_dir accepts string path."""
    output = tmp_path / "test.db"

    build_database(str(single_run_dir), output)

    assert output.exists()


def test_pathlib_path_is_accepted_for_data_dir(single_run_dir, tmp_path):
    """Test that data_dir accepts Path object."""
    output = tmp_path / "test.db"

    build_database(Path(single_run_dir), output)

    assert output.exists()


def test_string_path_is_accepted_for_output(single_run_dir, tmp_path):
    """Test that output accepts string path."""
    output = tmp_path / "test.db"

    build_database(single_run_dir, str(output))

    assert output.exists()


def test_pathlib_path_is_accepted_for_output(single_run_dir, tmp_path):
    """Test that output accepts Path object."""
    output = tmp_path / "test.db"

    build_database(single_run_dir, Path(output))

    assert output.exists()


# Error handling tests


def test_missing_metadata_file_raises_error(temp_data_dir, sample_csv_data, tmp_path):
    """Test that missing run_metadata.json raises FileNotFoundError."""
    run_dir = temp_data_dir / "25.10.06_run_1_10h41"
    run_dir.mkdir()
    # Only create CSV, no JSON
    sample_csv_data.to_csv(run_dir / "pressure_gauge_data.csv", index=False)

    output = tmp_path / "test.db"

    with pytest.raises(FileNotFoundError):
        build_database(temp_data_dir, output)


def test_missing_csv_file_raises_error(temp_data_dir, sample_metadata, tmp_path):
    """Test that missing pressure_gauge_data.csv raises FileNotFoundError."""
    run_dir = temp_data_dir / "25.10.06_run_1_10h41"
    run_dir.mkdir()
    # Only create JSON, no CSV
    with open(run_dir / "run_metadata.json", "w") as f:
        json.dump(sample_metadata, f)

    output = tmp_path / "test.db"

    with pytest.raises(FileNotFoundError):
        build_database(temp_data_dir, output)


def test_malformed_json_raises_error(temp_data_dir, sample_csv_data, tmp_path):
    """Test that malformed JSON file raises JSONDecodeError."""
    run_dir = temp_data_dir / "25.10.06_run_1_10h41"
    run_dir.mkdir()
    # Create malformed JSON
    with open(run_dir / "run_metadata.json", "w") as f:
        f.write("{invalid json")
    sample_csv_data.to_csv(run_dir / "pressure_gauge_data.csv", index=False)

    output = tmp_path / "test.db"

    with pytest.raises(json.JSONDecodeError):
        build_database(temp_data_dir, output)


def test_empty_data_directory(temp_data_dir, tmp_path):
    """Test that empty data directory creates empty database."""
    output = tmp_path / "test.db"

    build_database(temp_data_dir, output)

    with sqlite3.connect(output) as conn:
        cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM runs")
    run_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM measurements")
    meas_count = cursor.fetchone()[0]
    assert run_count == 0
    assert meas_count == 0


def test_nonexistent_data_directory_raises_error(tmp_path):
    """Test that nonexistent data directory raises appropriate error."""
    nonexistent_dir = tmp_path / "nonexistent"
    output = tmp_path / "test.db"

    with pytest.raises((FileNotFoundError, AttributeError)):
        build_database(nonexistent_dir, output)
