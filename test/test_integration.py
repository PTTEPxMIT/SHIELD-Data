"""Integration and system tests for SHIELD-Data package.

Tests cover:
- End-to-end database building and loading
- Integration between build_db and db modules
- Real data flow through the system
"""

import json
import subprocess
import sys

import pandas as pd
import pytest


@pytest.fixture
def sample_run_data(tmp_path):
    """Create sample run data structure in tmp directory."""
    data_dir = tmp_path / "run_data"
    data_dir.mkdir()

    # Create first run
    run1_dir = data_dir / "25.11.20_run_1_14h30"
    run1_dir.mkdir()

    metadata1 = {
        "run_info": {
            "date": "2025-11-20",
            "start_time": "14:30:00",
            "run_type": "permeation_exp",
            "furnace_setpoint": 600,
            "material": "tungsten",
            "coating": "AlCrN",
        },
        "gauges": {"WGM701": "upstream"},
        "thermocouples": {"TC1": "furnace"},
    }

    with open(run1_dir / "run_metadata.json", "w") as f:
        json.dump(metadata1, f)

    df1 = pd.DataFrame(
        {
            "RealTimestamp": [
                "2025-11-20 14:30:00",
                "2025-11-20 14:30:01",
                "2025-11-20 14:30:02",
            ],
            "WGM701_Voltage (V)": [1.5, 1.6, 1.7],
            "CVM211_Voltage (V)": [2.5, 2.6, 2.7],
            "Baratron626D_1KT_Voltage (V)": [3.5, 3.6, 3.7],
            "Baratron626D_1T_Voltage (V)": [4.5, 4.6, 4.7],
        }
    )
    df1.to_csv(run1_dir / "shield_data.csv", index=False)

    # Create second run
    run2_dir = data_dir / "25.11.21_run_2_09h15"
    run2_dir.mkdir()

    metadata2 = {
        "run_info": {
            "date": "2025-11-21",
            "start_time": "09:15:00",
            "run_type": "calibration",
            "furnace_setpoint": 400,
            "material": "steel",
            "coating": "None",
        },
        "gauges": {"WGM701": "upstream"},
        "thermocouples": {"TC1": "furnace"},
    }

    with open(run2_dir / "run_metadata.json", "w") as f:
        json.dump(metadata2, f)

    df2 = pd.DataFrame(
        {
            "RealTimestamp": ["2025-11-21 09:15:00", "2025-11-21 09:15:01"],
            "WGM701_Voltage (V)": [5.1, 5.2],
            "CVM211_Voltage (V)": [6.1, 6.2],
            "Baratron626D_1KT_Voltage (V)": [7.1, 7.2],
            "Baratron626D_1T_Voltage (V)": [8.1, 8.2],
        }
    )
    df2.to_csv(run2_dir / "shield_data.csv", index=False)

    return data_dir


# Integration Tests


def test_build_and_load_database_integration(sample_run_data, tmp_path):
    """Test building database and loading data through the API."""
    from shield_data import build_db, db

    db_path = tmp_path / "test_shield.db"

    # Build database
    build_db.build_database(sample_run_data, db_path)

    assert db_path.exists()

    # Override DB_PATH for testing
    original_path = db.DB_PATH
    db.DB_PATH = db_path

    try:
        # Load catalogue
        cat = db.catalogue()
        assert len(cat) == 2
        assert "25.11.20_run_1_14h30" in cat["run_id"].values
        assert "25.11.21_run_2_09h15" in cat["run_id"].values

        # Load specific run
        run1_data = db.load("25.11.20_run_1_14h30")
        assert len(run1_data) == 3
        assert all(run1_data["run_id"] == "25.11.20_run_1_14h30")

        # Load metadata
        metadata = db.load_metadata("25.11.20_run_1_14h30")
        assert metadata["run_info"]["furnace_setpoint"] == 600
        assert metadata["run_info"]["material"] == "tungsten"

        # Load filtered
        filtered = db.load_filtered(furnace_setpoint=600)
        assert len(filtered) == 3
        assert all(filtered["run_id"] == "25.11.20_run_1_14h30")

    finally:
        db.DB_PATH = original_path


def test_multiple_builds_produce_consistent_results(sample_run_data, tmp_path):
    """Test that rebuilding database produces identical results."""
    from shield_data import build_db, db

    db_path1 = tmp_path / "test1.db"
    db_path2 = tmp_path / "test2.db"

    # Build database twice
    build_db.build_database(sample_run_data, db_path1)
    build_db.build_database(sample_run_data, db_path2)

    # Compare sizes
    assert db_path1.stat().st_size == db_path2.stat().st_size

    # Load and compare data
    original_path = db.DB_PATH

    try:
        # Load from first database
        db.DB_PATH = db_path1
        cat1 = db.catalogue()
        data1 = db.load("25.11.20_run_1_14h30")

        # Load from second database
        db.DB_PATH = db_path2
        cat2 = db.catalogue()
        data2 = db.load("25.11.20_run_1_14h30")

        # Compare
        pd.testing.assert_frame_equal(cat1, cat2)
        pd.testing.assert_frame_equal(data1, data2)

    finally:
        db.DB_PATH = original_path


def test_filtered_load_across_multiple_runs(sample_run_data, tmp_path):
    """Test load_filtered combines data from multiple runs correctly."""
    from shield_data import build_db, db

    db_path = tmp_path / "test.db"
    build_db.build_database(sample_run_data, db_path)

    original_path = db.DB_PATH
    db.DB_PATH = db_path

    try:
        # Filter by run_type that matches multiple runs
        all_data = db.load_filtered(run_type="permeation_exp")
        assert len(all_data) == 3  # Only run 1

        calibration_data = db.load_filtered(run_type="calibration")
        assert len(calibration_data) == 2  # Only run 2

        # Verify run_ids
        assert all(all_data["run_id"] == "25.11.20_run_1_14h30")
        assert all(calibration_data["run_id"] == "25.11.21_run_2_09h15")

    finally:
        db.DB_PATH = original_path


# System Tests


def test_full_workflow_with_real_structure(sample_run_data, tmp_path):
    """Test complete workflow: build, query, filter, and verify."""
    from shield_data import build_db, db

    db_path = tmp_path / "full_workflow.db"

    # Step 1: Build database
    build_db.build_database(sample_run_data, db_path)

    original_path = db.DB_PATH
    db.DB_PATH = db_path

    try:
        # Step 2: Verify catalogue
        cat = db.catalogue()
        assert len(cat) == 2
        assert set(cat.columns) == {
            "run_id",
            "date",
            "start_time",
            "run_type",
            "furnace_setpoint",
            "material",
            "coating",
            "metadata",
        }

        # Step 3: Load individual runs
        for run_id in cat["run_id"]:
            data = db.load(run_id)
            assert not data.empty
            assert all(data["run_id"] == run_id)

            metadata = db.load_metadata(run_id)
            assert "run_info" in metadata
            assert "gauges" in metadata
            assert "thermocouples" in metadata

        # Step 4: Filter by different criteria
        tungsten_runs = db.load_filtered(material="tungsten")
        assert len(tungsten_runs) == 3

        steel_runs = db.load_filtered(material="steel")
        assert len(steel_runs) == 2

        # Step 5: Verify data integrity
        total_measurements = sum(len(db.load(rid)) for rid in cat["run_id"])
        assert total_measurements == 5  # 3 + 2

    finally:
        db.DB_PATH = original_path


def test_database_handles_missing_optional_fields(tmp_path):
    """Test system works with minimal metadata."""
    from shield_data import build_db, db

    data_dir = tmp_path / "run_data"
    data_dir.mkdir()

    run_dir = data_dir / "25.11.21_run_1_10h00"
    run_dir.mkdir()

    # Minimal metadata (only required fields)
    metadata = {
        "run_info": {
            "date": "2025-11-21",
            "start_time": "10:00:00",
            "run_type": "test",
            "furnace_setpoint": 500,
        },
        "gauges": {},
        "thermocouples": {},
    }

    with open(run_dir / "run_metadata.json", "w") as f:
        json.dump(metadata, f)

    df = pd.DataFrame(
        {
            "RealTimestamp": ["2025-11-21 10:00:00"],
            "WGM701_Voltage (V)": [1.0],
            "CVM211_Voltage (V)": [2.0],
            "Baratron626D_1KT_Voltage (V)": [3.0],
            "Baratron626D_1T_Voltage (V)": [4.0],
        }
    )
    df.to_csv(run_dir / "shield_data.csv", index=False)

    db_path = tmp_path / "minimal.db"
    build_db.build_database(data_dir, db_path)

    original_path = db.DB_PATH
    db.DB_PATH = db_path

    try:
        cat = db.catalogue()
        assert len(cat) == 1
        # Optional fields should be None or null
        assert pd.isna(cat.iloc[0]["material"]) or cat.iloc[0]["material"] is None

    finally:
        db.DB_PATH = original_path


def test_large_dataset_performance(tmp_path):
    """Test system handles larger dataset efficiently."""
    from shield_data import build_db, db

    data_dir = tmp_path / "run_data"
    data_dir.mkdir()

    run_dir = data_dir / "25.11.21_run_1_12h00"
    run_dir.mkdir()

    metadata = {
        "run_info": {
            "date": "2025-11-21",
            "start_time": "12:00:00",
            "run_type": "long_run",
            "furnace_setpoint": 700,
            "material": "titanium",
            "coating": "TiAlN",
        },
        "gauges": {"WGM701": "upstream"},
        "thermocouples": {"TC1": "furnace"},
    }

    with open(run_dir / "run_metadata.json", "w") as f:
        json.dump(metadata, f)

    # Create large dataset (1000 measurements)
    n_measurements = 1000
    timestamps = [
        f"2025-11-21 12:00:{i:02d}"
        if i < 60
        else f"2025-11-21 12:{i // 60:02d}:{i % 60:02d}"
        for i in range(n_measurements)
    ]
    df = pd.DataFrame(
        {
            "RealTimestamp": timestamps,
            "WGM701_Voltage (V)": [1.0 + i * 0.001 for i in range(n_measurements)],
            "CVM211_Voltage (V)": [2.0 + i * 0.001 for i in range(n_measurements)],
            "Baratron626D_1KT_Voltage (V)": [
                3.0 + i * 0.001 for i in range(n_measurements)
            ],
            "Baratron626D_1T_Voltage (V)": [
                4.0 + i * 0.001 for i in range(n_measurements)
            ],
        }
    )
    df.to_csv(run_dir / "shield_data.csv", index=False)

    db_path = tmp_path / "large.db"

    # Build should complete without errors
    build_db.build_database(data_dir, db_path)
    assert db_path.exists()

    original_path = db.DB_PATH
    db.DB_PATH = db_path

    try:
        # Load should handle large dataset
        data = db.load("25.11.21_run_1_12h00")
        assert len(data) == n_measurements
        assert data["WGM701_voltage"].iloc[0] == 1.0
        assert data["WGM701_voltage"].iloc[-1] == 1.0 + (n_measurements - 1) * 0.001

    finally:
        db.DB_PATH = original_path
