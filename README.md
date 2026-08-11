# SHIELD-Data
[![CI](https://github.com/PTTEPxMIT/SHIELD-Data/actions/workflows/ci_conda.yml/badge.svg)](https://github.com/PTTEPxMIT/SHIELD-Data/actions/workflows/ci_conda.yml)
[![codecov](https://codecov.io/gh/PTTEPxMIT/SHIELD-Data/graph/badge.svg?token=mDUOcHgDN5)](https://codecov.io/gh/PTTEPxMIT/SHIELD-Data)
[![Code style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![DOI](https://zenodo.org/badge/1041646727.svg)](https://doi.org/10.5281/zenodo.17544506)

A Python package providing experimental permeation data from the SHIELD hydrogen permeation rig.

## Overview

SHIELD-Data bundles experimental data in an SQLite database for easy access and analysis. The package includes:

- **826,000+ measurements** from 8 experimental runs
- **SQLite database** for efficient querying and filtering
- **Simple API** for loading data and metadata
- **Bundled with pip install** - no external data downloads needed

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
#   run_id, date, start_time, run_type, furnace_setpoint, material, coating
```

### `load(run_id)`
Load pressure gauge data for a specific run.

```python
df = sd.load("25.10.06_run_1_10h41")
# Returns DataFrame with columns:
#   timestamp, WGM701_voltage, CVM211_voltage,
#   Baratron626D_1KT_voltage, Baratron626D_1T_voltage, run_id
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

### Database Schema

The SQLite database contains two tables:

**runs table:**
- `run_id` (TEXT, PRIMARY KEY)
- `date` (TEXT)
- `start_time` (TEXT)
- `run_type` (TEXT)
- `furnace_setpoint` (INTEGER)
- `material` (TEXT, nullable)
- `coating` (TEXT, nullable)
- `metadata` (TEXT, JSON)

**measurements table:**
- `id` (INTEGER, PRIMARY KEY)
- `run_id` (TEXT, FOREIGN KEY)
- `timestamp` (TEXT)
- `WGM701_voltage` (REAL)
- `CVM211_voltage` (REAL)
- `Baratron626D_1KT_voltage` (REAL)
- `Baratron626D_1T_voltage` (REAL)

### Run Metadata

Each run includes detailed metadata:
- Run information (type, date, furnace setpoint)
- Gauge configurations (4 pressure gauges)
- Valve timing information
- Recording parameters

## Repository Structure

```
SHIELD-Data/
├── run_data/                     # Raw data (not in package)
│   ├── YY.MM.DD_run_X_HHhMM/    # Individual run folders
│   │   ├── pressure_gauge_data.csv
│   │   └── run_metadata.json
│   └── ...
├── src/shield_data/
│   ├── db.py                     # Main API
│   └── build_db.py               # Database builder
└── test/                         # Unit tests
```

The SQLite database itself is not stored in git: CI builds it from `run_data/`
and publishes it to the [`data-latest` release](https://github.com/PTTEPxMIT/SHIELD-Data/releases/tag/data-latest).
The package downloads and caches it on first use; refresh with
`shield_data.update_database()`, or pin a local file via the `SHIELD_DATA_DB`
environment variable.

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

To rebuild the database from raw data:

```python
from shield_data.build_db import build_database

build_database("run_data")  # Creates src/shield_data/shield_data.db
```

## Requirements

- Python >= 3.9
- pandas

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
