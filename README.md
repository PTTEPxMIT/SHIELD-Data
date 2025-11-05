# SHIELD-Data

A repository to store and manage raw experimental data produced from the SHIELD permeation rig.

## Overview

This repository provides an automated data management system for SHIELD experimental runs. It includes:

- **Automated Data Upload**: Watchdog-based monitoring system that detects new experimental data and automatically creates GitHub pull requests
- **Data Cataloging**: Automatic generation of a searchable catalogue (CSV + README) containing metadata for all experimental runs
- **Structured Storage**: Organized folder structure with run metadata, pressure gauge data, and backups
- **PR-based Workflow**: All data additions are tracked through GitHub pull requests with detailed metadata

## Repository Structure

```
SHIELD-Data/
├── run_data/                          # Main data storage folder
│   ├── YY.MM.DD_run_X_HHhMM/         # Individual run folders
│   │   ├── pressure_gauge_data.csv   # Experimental measurements
│   │   ├── run_metadata.json         # Run configuration and metadata
│   │   └── backup/                   # Backup data files
│   ├── runs_catalogue.csv            # Auto-generated catalogue
│   └── README.md                     # Auto-generated table view of catalogue
└── src/shield_data/                  # Python package
    ├── data_upload_handler.py        # Watchdog monitoring and PR creation
    ├── build_catalogue.py            # Catalogue generation
    └── pr_template.md                # PR body template
```

## Features

### Automated Data Upload

The `upload_data_from_folder()` function monitors a specified folder for new experimental data and automatically:

1. Detects new or modified run data
2. Validates folder structure and metadata
3. Creates a git branch and commits changes
4. Regenerates the data catalogue
5. Opens a pull request with detailed run information

### Data Catalogue

Every time data is added, the catalogue is automatically updated with:
- Run ID (folder name)
- Relative path to data
- Run type (e.g., permeation_exp)
- Date
- Furnace setpoint
- Material (if available)
- Coating (if available)

### Run Metadata

Each experimental run includes a `run_metadata.json` file containing:
- Run information (type, date, furnace setpoint, etc.)
- Gauge configurations
- Valve timing information
- Recording parameters

## Usage

### Installing the Package

```bash
pip install -e .
```

### Monitoring for New Data

```python
from shield_data import upload_data_from_folder

# Monitor the run_data folder with default settings
upload_data_from_folder("run_data")

# Custom monitoring intervals
upload_data_from_folder(
    "run_data",
    check_interval=5,    # Check every 5 seconds
    batch_delay=2        # Wait 2 seconds after last change before processing
)
```

### Building the Catalogue

```python
from shield_data import build_catalogue

# Regenerate the catalogue manually
build_catalogue("run_data")
```

### Loading and Analyzing Data

The package provides simple functions to load and filter experimental data:

#### View the Catalogue

```python
from shield_data import catalogue

# Load the catalogue as a pandas DataFrame
cat = catalogue()
print(cat)
```

#### Load a Specific Run

```python
from shield_data import load

# Load pressure gauge data for a specific run
df = load("25.10.06_run_1_10h41")

# The DataFrame includes all measurement data plus a 'run_id' column
print(df.head())
```

#### Load Run Metadata

```python
from shield_data import load_metadata

# Load the metadata JSON as a dictionary
metadata = load_metadata("25.10.06_run_1_10h41")

# Access specific metadata fields
run_info = metadata["run_info"]
print(f"Run type: {run_info['run_type']}")
print(f"Furnace setpoint: {run_info['furnace_setpoint']} K")
print(f"Start time: {run_info['start_time']}")
```

#### Filter and Load Multiple Runs

```python
from shield_data import load_filtered

# Load all runs at a specific temperature
df_500k = load_filtered(furnace_setpoint=500)

# Load runs by type and date
df_oct6 = load_filtered(run_type="permeation_exp", date="2025-10-06")

# Filter by material (when available)
df_material = load_filtered(material="stainless_steel")

# The result is a combined DataFrame with data from all matching runs
print(f"Loaded {len(df_500k)} data points from {df_500k['run_id'].nunique()} runs")
```

#### Example Analysis Workflow

```python
from shield_data import catalogue, load_filtered
import matplotlib.pyplot as plt

# View available runs
cat = catalogue()
print(cat[["run_id", "date", "furnace_setpoint"]])

# Load all 500K experiments
df = load_filtered(furnace_setpoint=500)

# Group by run and plot
for run_id in df["run_id"].unique():
    run_data = df[df["run_id"] == run_id]
    plt.plot(run_data["time"], run_data["pressure"], label=run_id)

plt.xlabel("Time (s)")
plt.ylabel("Pressure")
plt.legend()
plt.show()
```

## Requirements

- Python >= 3.9
- watchdog
- jinja2
- pandas
- Git
- GitHub CLI (`gh`) configured with authentication
