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
- **A small catalogue** (~1 MB) for browsing and filtering runs by material, coating, furnace setpoint, recorded channels, ...
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
#   material, coating, channels, n_measurements, data_file, size_bytes,
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
- Gauge configurations (4 pressure gauges)
- Valve timing information
- Recording parameters

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

When adding new experimental runs:

1. Add run folder to `run_data/YY.MM.DD_run_X_HHhMM/`
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
