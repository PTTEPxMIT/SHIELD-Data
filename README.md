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

## Requirements

- Python >= 3.9
- watchdog
- jinja2
- Git
- GitHub CLI (`gh`) configured with authentication
