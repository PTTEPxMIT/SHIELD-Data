"""Unit tests for store.py and the store-mode (per-run Parquet) API in db.py.

Tests cover:
- CSV -> Parquet conversion with exact round-trip verification
- Reading run folders in either storage format
- Catalogue building (normalised fields, channels, checksums)
- Store-mode catalogue/load/load_metadata/load_filtered
- Per-run download, checksum verification, and caching
"""

import hashlib
import json
import urllib.error

import pandas as pd
import pytest

from shield_data import db, store

GAUGE_COLUMNS = [
    "WGM701_Voltage (V)",
    "CVM211_Voltage (V)",
    "Baratron626D_1KT_Voltage (V)",
    "Baratron626D_1T_Voltage (V)",
]


def _write_run(
    data_dir,
    run_id,
    n_rows=3,
    with_temperature=False,
    material_key="material",
    material="steel",
):
    """Create a legacy CSV run folder and return its path."""
    run_dir = data_dir / run_id
    run_dir.mkdir(parents=True)

    metadata = {
        "run_info": {
            "date": "2025-10-06",
            "start_time": "10:41:00",
            "run_type": "permeation_exp",
            "furnace_setpoint": 500,
            material_key: material,
            "coating": "TiN",
        },
        "gauges": {"WGM701": "info"},
        "thermocouples": {"TC1": "info"},
    }
    with open(run_dir / store.METADATA_FILENAME, "w") as f:
        json.dump(metadata, f)

    data = {
        "RealTimestamp": [
            f"2025-10-06 10:41:{i:02d}.{i * 111 % 1000:03d}" for i in range(n_rows)
        ]
    }
    if with_temperature:
        data["Local_temperature (C)"] = [20.0 + i * 0.1 for i in range(n_rows)]
        data["furnace_thermocouple_Voltage (mV)"] = [
            1.234567890123 + i for i in range(n_rows)
        ]
    for j, col in enumerate(GAUGE_COLUMNS):
        data[col] = [j + i * 0.0012345678901234 for i in range(n_rows)]

    pd.DataFrame(data).to_csv(run_dir / store.LEGACY_CSV_FILENAME, index=False)
    return run_dir


@pytest.fixture
def data_dir(tmp_path):
    """run_data with one legacy CSV run and one converted Parquet run."""
    root = tmp_path / "run_data"
    _write_run(root, "25.10.06_run_1_10h41", material="steel")
    run2 = _write_run(
        root,
        "25.10.07_run_1_08h16",
        with_temperature=True,
        material_key="sample_material",
        material="aluminum",
    )
    store.convert_run(run2, delete_csv=True)
    return root


@pytest.fixture
def store_mode(tmp_path, monkeypatch):
    """Point db at an isolated cache with no pinned database (store mode)."""
    monkeypatch.delenv(db.DB_ENV_VAR, raising=False)
    monkeypatch.delenv(db.CATALOGUE_ENV_VAR, raising=False)
    monkeypatch.setattr(db, "DB_PATH", None)
    monkeypatch.setattr(db, "CATALOGUE_PATH", None)
    cache = tmp_path / "cache"
    monkeypatch.setattr(db, "_cache_dir", lambda: cache)
    monkeypatch.setattr(db, "_CATALOGUE_MEMO", {})
    return cache


# --- conversion -------------------------------------------------------------


def test_convert_run_round_trip_is_exact(tmp_path):
    run_dir = _write_run(tmp_path / "run_data", "25.10.06_run_1_10h41", n_rows=50)
    original = pd.read_csv(run_dir / store.LEGACY_CSV_FILENAME)

    parquet_path = store.convert_run(run_dir)

    back = pd.read_parquet(parquet_path)
    assert len(back) == 50
    for col in GAUGE_COLUMNS:
        assert back[col].equals(original[col])  # bit-identical float64
    assert pd.api.types.is_datetime64_any_dtype(back["RealTimestamp"])
    assert back["RealTimestamp"].iloc[1] == pd.Timestamp("2025-10-06 10:41:01.111")


def test_convert_run_keeps_csv_by_default(tmp_path):
    run_dir = _write_run(tmp_path / "run_data", "25.10.06_run_1_10h41")
    store.convert_run(run_dir)
    assert (run_dir / store.LEGACY_CSV_FILENAME).exists()


def test_convert_run_deletes_csv_when_asked(tmp_path):
    run_dir = _write_run(tmp_path / "run_data", "25.10.06_run_1_10h41")
    store.convert_run(run_dir, delete_csv=True)
    assert not (run_dir / store.LEGACY_CSV_FILENAME).exists()
    assert (run_dir / store.MEASUREMENTS_FILENAME).exists()


def test_convert_preserves_extra_channels(tmp_path):
    run_dir = _write_run(
        tmp_path / "run_data", "25.10.06_run_1_10h41", with_temperature=True
    )
    store.convert_run(run_dir, delete_csv=True)
    df = store.read_measurements(run_dir)
    assert "Local_temperature (C)" in df.columns
    assert "furnace_thermocouple_Voltage (mV)" in df.columns


def test_read_measurements_same_for_both_formats(tmp_path):
    run_dir = _write_run(tmp_path / "run_data", "25.10.06_run_1_10h41", n_rows=10)
    from_csv = store.read_measurements(run_dir)
    store.convert_run(run_dir, delete_csv=True)
    from_parquet = store.read_measurements(run_dir)
    pd.testing.assert_frame_equal(from_csv, from_parquet, check_dtype=False)


def test_data_file_missing_raises(tmp_path):
    empty = tmp_path / "run_data" / "25.10.06_run_1_10h41"
    empty.mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        store.data_file(empty)


def test_convert_cli_converts_whole_directory(tmp_path, capsys):
    root = tmp_path / "run_data"
    _write_run(root, "25.10.06_run_1_10h41")
    _write_run(root, "25.10.07_run_1_08h16")
    assert store.main(["convert", str(root), "--delete-csv"]) == 0
    assert (root / "25.10.06_run_1_10h41" / store.MEASUREMENTS_FILENAME).exists()
    assert not (root / "25.10.06_run_1_10h41" / store.LEGACY_CSV_FILENAME).exists()
    assert "Converted 2 run(s)" in capsys.readouterr().out


# --- catalogue --------------------------------------------------------------


def test_build_catalogue_fields(data_dir):
    cat = store.build_catalogue(data_dir)

    assert list(cat["run_id"]) == ["25.10.06_run_1_10h41", "25.10.07_run_1_08h16"]
    run1 = cat.iloc[0]
    assert run1["material"] == "steel"
    assert run1["furnace_setpoint"] == 500
    assert run1["data_file"] == store.LEGACY_CSV_FILENAME
    assert set(run1["channels"]) == set(GAUGE_COLUMNS)

    # v1.3 metadata: material falls back to sample_material; extra channels listed
    run2 = cat.iloc[1]
    assert run2["material"] == "aluminum"
    assert run2["data_file"] == store.MEASUREMENTS_FILENAME
    assert "Local_temperature (C)" in list(run2["channels"])
    assert run2["n_measurements"] == 3

    # checksums match the actual files; metadata JSON is complete
    path = data_dir / run2["run_id"] / run2["data_file"]
    assert run2["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert json.loads(run2["metadata"])["run_info"]["run_type"] == "permeation_exp"


def test_build_catalogue_writes_parquet(data_dir, tmp_path):
    out = tmp_path / "catalogue.parquet"
    store.build_catalogue(data_dir, output=out)
    assert pd.read_parquet(out)["run_id"].tolist() == [
        "25.10.06_run_1_10h41",
        "25.10.07_run_1_08h16",
    ]


# --- store-mode API ---------------------------------------------------------


def test_catalogue_store_mode_from_local_dir(data_dir, store_mode, monkeypatch):
    monkeypatch.setattr(db, "RUN_DATA_DIR", data_dir)
    cat = db.catalogue()
    assert len(cat) == 2
    assert "channels" in cat.columns


def test_load_store_mode_from_local_dir(data_dir, store_mode, monkeypatch):
    monkeypatch.setattr(db, "RUN_DATA_DIR", data_dir)
    df = db.load("25.10.07_run_1_08h16")
    assert (df["run_id"] == "25.10.07_run_1_08h16").all()
    assert "Local_temperature (C)" in df.columns
    assert pd.api.types.is_datetime64_any_dtype(df["RealTimestamp"])


def test_load_metadata_store_mode(data_dir, store_mode, monkeypatch):
    monkeypatch.setattr(db, "RUN_DATA_DIR", data_dir)
    metadata = db.load_metadata("25.10.06_run_1_10h41")
    assert metadata["run_info"]["furnace_setpoint"] == 500


def test_load_metadata_store_mode_missing_run(data_dir, store_mode, monkeypatch):
    monkeypatch.setattr(db, "RUN_DATA_DIR", data_dir)
    with pytest.raises(KeyError):
        db.load_metadata("99.99.99_run_9_99h99")


def test_load_filtered_store_mode_aligns_channels(data_dir, store_mode, monkeypatch):
    monkeypatch.setattr(db, "RUN_DATA_DIR", data_dir)
    df = db.load_filtered(run_type="permeation_exp")
    assert set(df["run_id"]) == {"25.10.06_run_1_10h41", "25.10.07_run_1_08h16"}
    # run 1 has no temperature channel: aligned as NaN
    run1_rows = df[df["run_id"] == "25.10.06_run_1_10h41"]
    assert run1_rows["Local_temperature (C)"].isna().all()


def test_load_filtered_store_mode_by_material(data_dir, store_mode, monkeypatch):
    monkeypatch.setattr(db, "RUN_DATA_DIR", data_dir)
    df = db.load_filtered(material="aluminum")
    assert set(df["run_id"]) == {"25.10.07_run_1_08h16"}


def test_load_filtered_unknown_filter_raises(data_dir, store_mode, monkeypatch):
    monkeypatch.setattr(db, "RUN_DATA_DIR", data_dir)
    with pytest.raises(ValueError, match="Unknown filter"):
        db.load_filtered(substrate="unknown")


def test_load_filtered_no_matches_returns_empty(data_dir, store_mode, monkeypatch):
    monkeypatch.setattr(db, "RUN_DATA_DIR", data_dir)
    assert db.load_filtered(material="unobtainium").empty


# --- per-run download and caching -------------------------------------------


@pytest.fixture
def remote(data_dir, store_mode, monkeypatch, tmp_path):
    """Simulate a remote repo: no local run_data, runs served via _fetch."""
    monkeypatch.setattr(db, "RUN_DATA_DIR", tmp_path / "no_such_dir")

    cat_path = tmp_path / "catalogue.parquet"
    store.build_catalogue(data_dir, output=cat_path)
    monkeypatch.setattr(db, "CATALOGUE_PATH", cat_path)

    calls = []

    def fake_fetch(url):
        calls.append(url)
        prefix = f"{db.RAW_DATA_URL}/"
        if not url.startswith(prefix):
            raise urllib.error.URLError("unexpected url")
        run_id, name = url[len(prefix) :].split("/")
        path = data_dir / run_id / name
        if not path.exists():
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return path.read_bytes()

    monkeypatch.setattr(db, "_fetch", fake_fetch)
    return calls


def test_load_downloads_verifies_and_caches(remote, store_mode):
    df = db.load("25.10.07_run_1_08h16")
    assert len(df) == 3
    cached = store_mode / "runs" / "25.10.07_run_1_08h16" / store.MEASUREMENTS_FILENAME
    assert cached.exists()

    # Second load comes from the cache: no new fetches
    n_calls = len(remote)
    df2 = db.load("25.10.07_run_1_08h16")
    assert len(remote) == n_calls
    pd.testing.assert_frame_equal(df, df2)


def test_load_download_checksum_mismatch_raises(remote, store_mode, monkeypatch):
    real_fetch = db._fetch
    monkeypatch.setattr(db, "_fetch", lambda url: real_fetch(url) + b"tampered")
    with pytest.raises(RuntimeError, match="checksum"):
        db.load("25.10.07_run_1_08h16")


def test_load_missing_run_raises(remote):
    with pytest.raises(FileNotFoundError, match=r"99\.99\.99_run_9_99h99"):
        db.load("99.99.99_run_9_99h99")


def test_update_catalogue_downloads_and_caches(
    store_mode, data_dir, tmp_path, monkeypatch
):
    cat_path = tmp_path / "catalogue.parquet"
    store.build_catalogue(data_dir, output=cat_path)
    raw = cat_path.read_bytes()
    manifest = {
        "catalogue_sha256": hashlib.sha256(raw).hexdigest(),
        "runs": 2,
    }
    responses = {
        f"{db.DATA_RELEASE_URL}/manifest.json": json.dumps(manifest).encode(),
        f"{db.DATA_RELEASE_URL}/{store.CATALOGUE_FILENAME}": raw,
    }
    monkeypatch.setattr(db, "_fetch", lambda url: responses[url])

    path = db.update_catalogue()
    assert pd.read_parquet(path)["run_id"].tolist() == [
        "25.10.06_run_1_10h41",
        "25.10.07_run_1_08h16",
    ]

    # Catalogue-less release raises a helpful error
    responses[f"{db.DATA_RELEASE_URL}/manifest.json"] = json.dumps({"runs": 2}).encode()
    (store_mode / "catalogue_manifest.json").unlink()
    with pytest.raises(RuntimeError, match="does not include a catalogue"):
        db.update_catalogue()


def test_update_catalogue_checksum_mismatch_raises(store_mode, monkeypatch):
    manifest = {"catalogue_sha256": "0" * 64}
    responses = {
        f"{db.DATA_RELEASE_URL}/manifest.json": json.dumps(manifest).encode(),
        f"{db.DATA_RELEASE_URL}/{store.CATALOGUE_FILENAME}": b"not a catalogue",
    }
    monkeypatch.setattr(db, "_fetch", lambda url: responses[url])
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        db.update_catalogue()
