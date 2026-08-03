# Contributing to SHIELD-Data

## Adding New Experimental Data

When adding new experimental runs to the database:

### Required Steps

1. **Add run data** to the `run_data/` folder:
   ```
   run_data/
   └── YY.MM.DD_run_X_HHhMM/
       ├── pressure_gauge_data.csv
       └── run_metadata.json
   ```

2. **Commit the run folder** (and nothing else):
   ```bash
   git add run_data/YY.MM.DD_run_X_HHhMM/
   git commit -m "Add run YY.MM.DD_run_X_HHhMM"
   ```

3. **Create PR** with:
   - Description of the new run(s)
   - Any relevant experimental notes

4. **After merge, the database rebuilds itself.** CI builds `shield_data.db`
   from `run_data/` and publishes it to the rolling `data-latest` GitHub
   release. Installed packages pick it up with
   `python -c "import shield_data; shield_data.update_database()"`.

### ⚠️ Important

**Do not commit `src/shield_data/shield_data.db`** — CI rejects PRs that
include it. The database is a build artifact published to the `data-latest`
release, not a tracked file.

To test locally before opening the PR, build a scratch copy:
```bash
python src/shield_data/build_db.py --add run_data/YY.MM.DD_run_X_HHhMM --output /tmp/check.db
SHIELD_DATA_DB=/tmp/check.db python -c "import shield_data; print(shield_data.catalogue())"
```

### Automated Validation

When you open a PR, GitHub Actions will automatically:
- ✅ Detect whether your PR adds new data or modifies code
- ✅ Validate the structure of CSV and JSON files
- ✅ Verify required fields are present in metadata
- ✅ Reject the PR if `shield_data.db` was committed
- ✅ Ingest the changed runs into a scratch database and verify they load

The PR cannot be merged until all validation checks pass.

### Testing Your Changes

Before submitting the PR, verify the database works:

```python
import shield_data as sd

# Check your run appears in the catalogue
cat = sd.catalogue()
print(cat[cat["run_id"] == "YY.MM.DD_run_X_HHhMM"])

# Load the new run's data
df = sd.load("YY.MM.DD_run_X_HHhMM")
print(f"Loaded {len(df)} measurements")

# Check metadata
metadata = sd.load_metadata("YY.MM.DD_run_X_HHhMM")
print(metadata["run_info"])
```

## Code Contributions

For code changes to the package itself:

1. Make your changes
2. Run tests: `pytest`
3. Ensure code style: `ruff check .`
4. Update documentation if needed
5. Submit PR with clear description

## Questions?

Open an issue or contact darkj385@mit.edu
