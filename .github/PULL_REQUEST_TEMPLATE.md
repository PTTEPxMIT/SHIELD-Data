---
name: Add Experimental Data
about: Template for adding new experimental data
title: 'Add run: [RUN_ID]'
labels: data
assignees: ''

---

## ⚠️ Required Before Submitting

- [ ] Rebuilt database with `python src/shield_data/build_db.py`
- [ ] Committed updated `src/shield_data/shield_data.db`
- [ ] Verified new data loads correctly

## Run Information

**Run ID(s):** 
**Furnace Setpoint(s):** 
**Date(s):** 

## Database Build Output

```
✓ YY.MM.DD_run_X_HHhMM: XXXXX measurements

✓ Database created: src/shield_data/shield_data.db
  Runs: X
  Measurements: XXX,XXX
  Size: XX.XX MB
```

## Verification Test

```python
import shield_data as sd

# Verify run appears
cat = sd.catalogue()
print(cat[cat["run_id"] == "NEW_RUN_ID"])

# Verify data loads
df = sd.load("NEW_RUN_ID")
print(f"Loaded {len(df)} measurements")
```

## Notes

Any additional context about this run/data.
