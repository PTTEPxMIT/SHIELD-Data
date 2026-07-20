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

2. **Rebuild the database** (required before PR):
   ```bash
   python src/shield_data/build_db.py
   ```
   
   This will:
   - Create/update `src/shield_data/shield_data.db`
   - Show summary of runs and measurements added
   - Display final database size

3. **Commit both** the new data AND the updated database:
   ```bash
   git add run_data/YY.MM.DD_run_X_HHhMM/
   git add src/shield_data/shield_data.db
   git commit -m "Add run YY.MM.DD_run_X_HHhMM"
   ```

4. **Create PR** with:
   - Description of the new run(s)
   - Any relevant experimental notes
   - Verification that the database rebuilt successfully

### ⚠️ Important

**PRs that add data to `run_data/` without updating `shield_data.db` will not be merged.**

The database file must be rebuilt and committed with every data addition to ensure users get the latest data when installing the package.

### Automated Validation

When you open a PR, GitHub Actions will automatically:
- ✅ Detect whether your PR adds new data or modifies code
- ✅ Validate the structure of CSV and JSON files
- ✅ Verify required fields are present in metadata
- ✅ Check that the database was updated (if data was added)
- ✅ Test database integrity

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

## Branches and Pull Requests

`main` is protected — all changes land through a pull request, including your own.

Name branches `<initials>/<topic>`, e.g. `cw/fix-baratron-scaling`. The initials prefix
answers the question that actually comes up months later: whose branch is this, and is
it safe to delete?

```bash
git switch main && git pull
git switch -c cw/<topic>
# work, commit
git push -u origin cw/<topic>
gh pr create --template code_change.md   # or data_addition.md
```

PRs are squash-merged, so the PR title becomes the commit subject on `main` — write it
as the message you'd want to read in `git log`.

## Code Contributions

For code changes to the package itself:

1. Make your changes
2. Run tests: `pytest`
3. Ensure code style: `ruff check .`
4. Update documentation if needed
5. Submit PR with clear description

## Questions?

Open an issue or contact darkj385@mit.edu
