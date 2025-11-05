import csv
from pathlib import Path

import pytest

from shield_data.build_catalogue import build_catalogue


def write_csv(path: Path, headers: list[str], rows: list[list[str]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)


def write_json(path: Path, content: dict):
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content), encoding="utf-8")


def test_build_catalogue_creates_csv_file(tmp_path: Path):
    """Test that build_catalogue creates the runs_catalogue.csv file.

    The catalogue CSV file is the primary output and must be created for the
    catalogue to be usable. This verifies the file is created in the expected
    location (inside runs_dir).
    """
    runs_dir = tmp_path / "run_data"
    run1 = runs_dir / "24.10.31_run_1_12h30"
    write_csv(run1 / "pressure_gauge_data.csv", ["t", "p"], [[0, 1.0]])

    build_catalogue(runs_dir)

    out_csv = runs_dir / "runs_catalogue.csv"
    assert out_csv.exists()


def test_build_catalogue_creates_readme_file(tmp_path: Path):
    """Test that build_catalogue creates a README.md file.

    The README provides human-readable documentation of available runs and
    should be created alongside the CSV catalogue for easy browsing in file
    explorers and version control.
    """
    runs_dir = tmp_path / "run_data"
    run1 = runs_dir / "24.10.31_run_1_12h30"
    write_csv(run1 / "pressure_gauge_data.csv", ["t", "p"], [[0, 1.0]])

    build_catalogue(runs_dir)

    readme = runs_dir / "README.md"
    assert readme.exists()


def test_build_catalogue_csv_has_correct_columns(tmp_path: Path):
    """Test that the CSV file has the correct column headers.

    The catalogue schema defines specific columns in a specific order.
    This verifies the CSV header row matches the expected schema, ensuring
    compatibility with code that reads the catalogue.
    """
    runs_dir = tmp_path / "run_data"
    run1 = runs_dir / "24.10.31_run_1_12h30"
    write_csv(run1 / "pressure_gauge_data.csv", ["t", "p"], [[0, 1.0]])

    build_catalogue(runs_dir)

    out_csv = runs_dir / "runs_catalogue.csv"
    with out_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        list(reader)  # consume to set fieldnames
        assert reader.fieldnames == [
            "run_id",
            "path",
            "run_type",
            "date",
            "furnace_setpoint",
            "material",
            "coating",
        ]


def test_build_catalogue_counts_runs_correctly(tmp_path: Path):
    """Test that build_catalogue includes all valid runs in the CSV.

    Each directory containing pressure_gauge_data.csv should be counted as
    a run and appear as a row in the catalogue. This verifies the discovery
    logic correctly identifies all runs.
    """
    runs_dir = tmp_path / "run_data"
    run1 = runs_dir / "24.10.31_run_1_12h30"
    run2 = runs_dir / "24.11.01_run_2_09h15"
    write_csv(run1 / "pressure_gauge_data.csv", ["t", "p"], [[0, 1.0]])
    write_csv(run2 / "pressure_gauge_data.csv", ["t", "p"], [[0, 2.0]])

    build_catalogue(runs_dir)

    out_csv = runs_dir / "runs_catalogue.csv"
    with out_csv.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2


def test_build_catalogue_uses_relative_paths(tmp_path: Path):
    """Test that run paths are stored relative to the parent directory.

    Paths should be relative (e.g., 'run_data/24.10.31_run_1_12h30') rather
    than absolute to make the catalogue portable across systems and prevent
    issues when the repository is cloned to different locations.
    """
    runs_dir = tmp_path / "run_data"
    run1 = runs_dir / "24.10.31_run_1_12h30"
    write_csv(run1 / "pressure_gauge_data.csv", ["t", "p"], [[0, 1.0]])

    build_catalogue(runs_dir)

    out_csv = runs_dir / "runs_catalogue.csv"
    with out_csv.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["path"] == f"run_data/{run1.name}"


def test_build_catalogue_uses_default_material_when_missing(tmp_path: Path):
    """Test that missing material metadata defaults to 'unknown'.

    When run_metadata.json is absent or doesn't contain a material field,
    the catalogue should use 'unknown' as a sensible default rather than
    leaving it blank or failing.
    """
    runs_dir = tmp_path / "run_data"
    run1 = runs_dir / "24.10.31_run_1_12h30"
    write_csv(run1 / "pressure_gauge_data.csv", ["t", "p"], [[0, 1.0]])

    build_catalogue(runs_dir)

    out_csv = runs_dir / "runs_catalogue.csv"
    with out_csv.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["material"] == "unknown"


def test_build_catalogue_uses_default_coating_when_missing(tmp_path: Path):
    """Test that missing coating metadata defaults to 'None'.

    When run_metadata.json is absent or doesn't contain a coating field,
    the catalogue should use 'None' to indicate no coating rather than
    leaving it blank or failing.
    """
    runs_dir = tmp_path / "run_data"
    run1 = runs_dir / "24.10.31_run_1_12h30"
    write_csv(run1 / "pressure_gauge_data.csv", ["t", "p"], [[0, 1.0]])

    build_catalogue(runs_dir)

    out_csv = runs_dir / "runs_catalogue.csv"
    with out_csv.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["coating"] == "None"


def test_build_catalogue_readme_shows_correct_count(tmp_path: Path):
    """Test that README displays the correct total run count.

    The README should show 'Total runs: N' where N matches the actual number
    of runs found. This provides quick visibility into the catalogue size
    without opening the CSV.
    """
    runs_dir = tmp_path / "run_data"
    run1 = runs_dir / "24.10.31_run_1_12h30"
    run2 = runs_dir / "24.11.01_run_2_09h15"
    write_csv(run1 / "pressure_gauge_data.csv", ["t", "p"], [[0, 1.0]])
    write_csv(run2 / "pressure_gauge_data.csv", ["t", "p"], [[0, 2.0]])

    build_catalogue(runs_dir)

    readme = runs_dir / "README.md"
    content = readme.read_text(encoding="utf-8")
    assert "Total runs: 2" in content


def test_build_catalogue_missing_dir_raises(tmp_path: Path):
    """Test that build_catalogue raises FileNotFoundError for missing directory.

    If the specified runs_dir doesn't exist, the function should fail
    immediately with a clear error rather than creating an empty catalogue.
    This helps catch configuration errors early.
    """
    with pytest.raises(FileNotFoundError):
        build_catalogue(tmp_path / "does_not_exist")


def test_build_catalogue_not_a_directory_raises(tmp_path: Path):
    """Test that build_catalogue raises NotADirectoryError for file paths.

    If the path points to a regular file instead of a directory, the function
    should raise NotADirectoryError. This prevents confusion when the wrong
    path is provided.
    """
    file_path = tmp_path / "not_a_dir.txt"
    file_path.write_text("test")
    with pytest.raises(NotADirectoryError):
        build_catalogue(file_path)


def test_build_catalogue_handles_malformed_json_uses_default_material(tmp_path: Path):
    """Test that malformed JSON metadata falls back to default material.

    If run_metadata.json contains invalid JSON, the function should handle
    the error gracefully and use default values ('unknown' for material)
    rather than crashing. This ensures robustness against corrupted files.
    """
    runs_dir = tmp_path / "run_data"
    run1 = runs_dir / "24.10.31_run_1_12h30"
    write_csv(run1 / "pressure_gauge_data.csv", ["t", "p"], [[0, 1.0]])
    (run1 / "run_metadata.json").write_text("{invalid json}", encoding="utf-8")

    build_catalogue(runs_dir)

    out_csv = runs_dir / "runs_catalogue.csv"
    with out_csv.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["material"] == "unknown"


def test_build_catalogue_empty_directory_creates_empty_csv(tmp_path: Path):
    """Test that build_catalogue creates an empty CSV when no runs exist.

    When runs_dir contains no valid run folders (i.e., no folders with
    pressure_gauge_data.csv), the catalogue should still be created but
    with zero data rows. This allows the catalogue structure to exist.
    """
    runs_dir = tmp_path / "run_data"
    runs_dir.mkdir(parents=True)
    (runs_dir / "not_a_run").mkdir()
    (runs_dir / "not_a_run" / "other_file.txt").write_text("test")

    build_catalogue(runs_dir)

    out_csv = runs_dir / "runs_catalogue.csv"
    with out_csv.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 0


def test_build_catalogue_empty_directory_readme_shows_zero_runs(tmp_path: Path):
    """Test that README shows 'Total runs: 0' when no runs found.

    The README should accurately reflect when no runs are present by
    displaying zero in the count. This helps users quickly identify an
    empty or not-yet-populated run directory.
    """
    runs_dir = tmp_path / "run_data"
    runs_dir.mkdir(parents=True)

    build_catalogue(runs_dir)

    readme = runs_dir / "README.md"
    content = readme.read_text(encoding="utf-8")
    assert "Total runs: 0" in content


def test_build_catalogue_empty_directory_readme_shows_no_runs_message(tmp_path: Path):
    """Test that README displays 'No runs found.' message when empty.

    When no runs exist, the README should show a helpful message instead of
    an empty table. This provides better user experience than a blank or
    confusing README.
    """
    runs_dir = tmp_path / "run_data"
    runs_dir.mkdir(parents=True)

    build_catalogue(runs_dir)

    readme = runs_dir / "README.md"
    content = readme.read_text(encoding="utf-8")
    assert "No runs found." in content
