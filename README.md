# SHIELD-Data
[![CI](https://github.com/PTTEPxMIT/SHIELD-Data/actions/workflows/ci_conda.yml/badge.svg)](https://github.com/PTTEPxMIT/SHIELD-Data/actions/workflows/ci_conda.yml)
[![codecov](https://codecov.io/gh/PTTEPxMIT/SHIELD-Data/graph/badge.svg?token=mDUOcHgDN5)](https://codecov.io/gh/PTTEPxMIT/SHIELD-Data)
[![Code style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![DOI](https://zenodo.org/badge/1041646727.svg)](https://doi.org/10.5281/zenodo.17544506)

A Python package providing experimental permeation data from the SHIELD hydrogen permeation rig.

## Overview

SHIELD-Data stores each experimental run as a compressed Parquet file and serves runs individually — you download only the runs you ask for, not the whole dataset. The package includes:

- **4.2M+ measurements** from 105+ experimental runs
- **Per-run Parquet storage**: every channel the rig recorded (gauge voltages, temperatures, future instruments), ~10x smaller than CSV, no schema migrations when instrumentation changes
- **A small catalogue** (~1 MB) for browsing and filtering runs by substrate, coating, furnace setpoint, recorded channels, ...
- **Simple API**: filter the catalogue, then `load()` fetches, verifies, and caches just those runs

## Installation

```bash
pip install shield-data
```

## Quick Start

```python
import shield_data as sd

# View all available runs
cat = sd.catalogue()
print(cat[["run_id", "date", "furnace_setpoint"]])

# Load data from a specific run
df = sd.load("25.10.06_run_1_10h41")

# Load all runs at 500K
df_500k = sd.load_filtered(furnace_setpoint=500)

# Get run metadata
metadata = sd.load_metadata("25.10.06_run_1_10h41")
print(metadata["run_info"])
```

## API Reference

### `catalogue()`
Load the catalogue of all experimental runs.

```python
cat = sd.catalogue()
# Returns DataFrame with columns:
#   run_id, date, start_time, end_time, run_type, furnace_setpoint,
#   substrate, coating, channels, n_measurements, data_file, size_bytes,
#   sha256, metadata
```

### `load(run_id)`
Load the measurements of a specific run. Only that run's file is downloaded
(verified against the catalogue checksum and cached locally).

```python
df = sd.load("25.10.06_run_1_10h41")
# Returns the channels exactly as the rig recorded them, e.g.:
#   RealTimestamp (datetime64), WGM701_Voltage (V), CVM211_Voltage (V),
#   Baratron626D_1KT_Voltage (V), Baratron626D_1T_Voltage (V),
#   Local_temperature (C), furnace_thermocouple_Voltage (mV), run_id
# Older runs recorded fewer channels — check catalogue()["channels"].
```

### `load_metadata(run_id)`
Load metadata for a specific run.

```python
metadata = sd.load_metadata("25.10.06_run_1_10h41")
# Returns dict with keys: version, run_info, gauges, thermocouples
```

### `load_filtered(**filters)`
Load data for runs matching filter criteria.

```python
# Filter by temperature
df = sd.load_filtered(furnace_setpoint=500)

# Filter by run type and date
df = sd.load_filtered(run_type="permeation_exp", date="2025-10-06")

# Multiple runs combined into single DataFrame
```

## Example Analysis

```python
import shield_data as sd
import matplotlib.pyplot as plt

# Load all 500K experiments
df = sd.load_filtered(furnace_setpoint=500)

# Plot pressure over time for each run
for run_id in df["run_id"].unique():
    run_data = df[df["run_id"] == run_id]
    plt.plot(run_data.index, run_data["Baratron626D_1T_voltage"], label=run_id)

plt.xlabel("Measurement Number")
plt.ylabel("Downstream Pressure (V)")
plt.legend()
plt.title("500K Permeation Experiments")
plt.show()
```

## Data Structure

### Storage Format

Each run folder holds two files:

- `measurements.parquet` — every channel the rig recorded, zstd-compressed.
  Parquet files are self-describing: column names and types are embedded, so
  runs with different instrumentation coexist without any schema migration.
- `run_metadata.json` — run info, gauge and thermocouple configuration.

The catalogue (built by CI, attached to the
[`data-latest` release](https://github.com/PTTEPxMIT/SHIELD-Data/releases/tag/data-latest))
has one row per run: normalised metadata fields, the list of recorded
`channels`, measurement counts, and each data file's sha256 (used to verify
per-run downloads). Refresh it with `shield_data.update_catalogue()`.

**Legacy SQLite database** (deprecated): the monolithic `shield_data.db` is
still built and released while downstream consumers migrate. Pinning it via
the `SHIELD_DATA_DB` environment variable preserves the old behaviour,
including the old `timestamp` / `*_voltage` column names. Note it carries
only the four original gauge-voltage columns — temperature channels are only
available through the Parquet path.

### Run Metadata

Each run includes detailed metadata:
- Run information (type, date, furnace setpoint)
- Sample description (substrate, coating layers, thickness)
- Gauge configurations (4 pressure gauges)
- Valve timing information
- Recording parameters

#### Sample description fields

Every run's `run_metadata.json` carries three sample description fields in
`run_info` (recorded by SHIELD_DAS since metadata version 1.4, and
backfilled into all earlier runs — see below):

- `sample_substrate` — substrate material, spelled out in full, e.g.
  `"carbon steel"`, `"316L steel"`.
- `sample_coating_layers` — the coating as a list of layers, ordered as
  named on the sample, each `{"material": ..., "thickness_nm": ...}` with
  materials spelled out in full (`"tungsten"`, `"silicon carbide"`,
  `"chromium"`, `"alumina"`). An uncoated sample has an empty list.
- `sample_coating` — human-readable summary derived from the layers, e.g.
  `"800nm tungsten"`, `"200nm tungsten + 50nm chromium"`; `"none"` for an
  uncoated sample.

The catalogue exposes `sample_substrate` and `sample_coating` as its
`substrate` and `coating` columns. Metadata versions ≤ 1.3 recorded a single
`material`/`sample_material` field instead, which readers treat as the
substrate.

#### Backfilled sample assignments (2026-08-11)

Runs recorded before metadata v1.4 either had no sample field or carried a
stale default (`sample_material: "316"` regardless of the mounted sample).
The sample description fields were backfilled for all 105 stored runs. The
assignments were inferred from the run groupings in the SHIELD analysis
notebook (`ShieldRunsAnalysis/SHIELD_analysis.ipynb`), cross-checked against
the `sample_thickness` eras in the recorded metadata, with two rulings
confirmed by the rig operator:

- The 26.03.19–26.03.27 tungsten-coated runs are **800nm** tungsten (the
  notebook block header; the `100nm_W_...` results CSV name is stale).
- Run 26.02.20 is 800nm tungsten coated (it is the sole run in the
  `800nm_W_coated_carbon_steel` results CSV, despite falling inside the
  uncoated carbon steel date range).

| Runs (inclusive date ranges) | Substrate | Coating |
| --- | --- | --- |
| 25.08.25 – 25.10.13, 25.11.05 – 25.11.18 (original sample), 25.11.19 – 25.12.10 (fresh sample) | 316L steel | none |
| 25.10.21 – 25.10.30 (original sample), 26.01.14 – 26.02.18 (fresh sample) | carbon steel | none |
| 26.02.20, 26.03.19 – 26.03.27 | carbon steel | 800nm tungsten |
| 26.04.01 – 26.04.09 | UKEA reference 316 steel | none |
| 26.04.11 – 26.04.15 | UKEA interface 316 steel | none |
| 26.04.17 – 26.04.23 | carbon steel | 100nm silicon carbide |
| 26.05.05 – 26.05.17 | carbon steel | 50nm tungsten |
| 26.05.20 | carbon steel | 200nm tungsten + 50nm chromium |
| 26.05.22 – 26.06.16 | carbon steel | 150nm alumina |

Supporting evidence: the `sample_thickness` recorded in v1.3 metadata is
constant within each sample era (0.008 m for the fresh 316L sample,
0.00065 m for the fresh carbon steel substrate also used for the 800nm
tungsten coating, 0.0005 m for both UKEA 316 samples, and 0.00136 m for the
carbon steel substrate used for the silicon carbide, 50nm tungsten,
tungsten+chromium, and alumina coatings).

During the backfill, v1.3 files were bumped to v1.4 (same layout plus the
sample fields, stale `sample_material` removed); v1.0/1.1 files keep their
version — their file layout predates v1.3 — but carry the same three
backfilled fields.

## Repository Structure

```
SHIELD-Data/
├── run_data/                     # Raw data (not in package)
│   ├── YY.MM.DD_run_X_HHhMM/    # Individual run folders
│   │   ├── measurements.parquet
│   │   └── run_metadata.json
│   └── ...
├── src/shield_data/
│   ├── db.py                     # Main API
│   ├── store.py                  # Parquet storage layer + catalogue builder
│   └── build_db.py               # Legacy database builder (deprecated)
└── test/                         # Unit tests
```

In a repo checkout, the API reads `run_data/` directly. Installed packages
fetch the catalogue from the `data-latest` release and individual runs from
the repository's raw URLs, caching everything per-user.

## Contributing

### Adding New Data

#### Uploading from the rig (normal path)

Runs recorded by [SHIELD_DAS](https://github.com/PTTEPxMIT/SHIELD_DAS) are
uploaded from the rig computer by hand after each run:

1. When the run has finished, double-click **`upload_runs.bat`** in the
   SHIELD_DAS folder on the rig PC (or run `shield-das-upload` in a
   terminal).
2. The uploader finds every completed run not yet uploaded, converts
   `shield_data.csv` to a zstd-compressed `measurements.parquet` (verified
   as an exact round-trip), drops the `backup/` directory, and opens one
   pull request per run against this repository (branch `auto/run-<run_id>`,
   folder `run_data/YY.MM.DD_run_X_HHhMM/`). Already-uploaded runs are
   skipped, so running it any time is safe.
3. Review and merge the PR once CI validation passes.
4. After merge, CI rebuilds the database and updates the
   [`data-latest` release](https://github.com/PTTEPxMIT/SHIELD-Data/releases/tag/data-latest);
   `shield_data.update_database()` then picks it up.

One-time setup (GitHub token + config) is documented in
[SHIELD_DAS docs/auto_upload.md](https://github.com/PTTEPxMIT/SHIELD_DAS/blob/main/docs/auto_upload.md).

#### Adding a run manually

For runs coming from anywhere else:

1. Copy the run folder to `run_data/YY.MM.DD_run_X_HHhMM/` containing
   `measurements.parquet` and `run_metadata.json` (no `backup/` directory) —
   convert a CSV with
   `python -m shield_data.store convert <run_folder> --delete-csv`
2. Commit the run folder and submit a PR (see [CONTRIBUTING.md](CONTRIBUTING.md))
3. After merge, CI rebuilds the database and updates the `data-latest` release

**Note:** do not commit `shield_data.db` — CI rejects PRs containing it.

### Development

To convert a legacy CSV run and rebuild the catalogue locally:

```bash
python -m shield_data.store convert run_data/YY.MM.DD_run_X_HHhMM --delete-csv
python -m shield_data.store catalogue run_data --output catalogue.parquet
```

## Requirements

- Python >= 3.9
- pandas, pyarrow

## License

Apache License 2.0

## Citation

If you use this data in your research, please cite:

```bibtex
@software{shield_data_2025,
  author = {Dark, James},
  title = {SHIELD-Data: Hydrogen Permeation Experimental Data},
  year = {2025},
  doi = {10.5281/zenodo.17544506},
  url = {https://github.com/PTTEPxMIT/SHIELD-Data}
}
```

## Contact

- **Author:** James Dark
- **Email:** darkj385@mit.edu
- **Repository:** https://github.com/PTTEPxMIT/SHIELD-Data
