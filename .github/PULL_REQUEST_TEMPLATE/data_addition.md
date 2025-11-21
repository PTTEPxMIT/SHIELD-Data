## Adding Experimental Data

### 📁 Files Added

Please confirm you've added the following to `run_data/`:

- [ ] `YY.MM.DD_run_X_HHhMM/pressure_gauge_data.csv`
- [ ] `YY.MM.DD_run_X_HHhMM/run_metadata.json`

### 🔄 Database Update

The automated checks will verify your data structure and notify you if the database needs rebuilding.

**If prompted to rebuild the database**, run:
```bash
python src/shield_data/build_db.py
```
and commit the changes

### 📝 Additional Context

Any experimental observations, special conditions, or notes about this data:

<!-- The bot will automatically post a summary with metadata extracted from your JSON files -->

---

**Automated checks will verify:**
- ✅ CSV and JSON file structure
- ✅ Required metadata fields present
- ✅ Database rebuild status
- ✅ Data integrity
