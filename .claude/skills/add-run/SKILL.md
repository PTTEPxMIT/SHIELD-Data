---
description: Add a new SHIELD permeation rig run to the database and rebuild
  shield_data.db. Use when the user has new run data, mentions a run folder like
  25.10.13_run_1_16h51, or asks to rebuild the database.
disable-model-invocation: true
argument-hint: [run-folder-name]
---

## Current state

- Branch: !`git branch --show-current`
- Runs present: !`ls run_data/ | wc -l`
- Status: !`git status --short`

## Steps

Add run `$ARGUMENTS` to the database.

1. **Check the branch.** If on `main`, stop and run `/new-feature` first — this needs a
   feature branch and a PR.

2. **Verify the run folder.** `run_data/$ARGUMENTS/` must contain both
   `pressure_gauge_data.csv` and `run_metadata.json`. If either is missing, stop and
   report — do not invent or scaffold them.

3. **Validate before building**, matching what `validate_data.yml` checks in CI, so
   failures surface locally rather than on the PR:
   - CSV has columns `RealTimestamp`, `WGM701_Voltage (V)`, `CVM211_Voltage (V)`,
     `Baratron626D_1KT_Voltage (V)`, `Baratron626D_1T_Voltage (V)`.
   - JSON has top-level keys `run_info`, `gauges`, `thermocouples`, and `run_info`
     contains `date`, `start_time`, `run_type`, `furnace_setpoint`.

4. **Record the before state:** run count and DB size.

5. **Rebuild:** `python src/shield_data/build_db.py`. Show its summary output. Note this
   rebuilds from scratch over every run, so it is slow and the whole DB file changes.

6. **Test:** `pytest test/`. Must pass.

7. **Sanity-check the new run loads:**
   ```python
   import shield_data as sd
   sd.catalogue()          # new run_id present?
   len(sd.load("$ARGUMENTS"))
   sd.load_metadata("$ARGUMENTS")["run_info"]
   ```

8. **Stage together** — `run_data/$ARGUMENTS/` and `src/shield_data/shield_data.db` must
   be in the same commit. CI fails a data addition without a rebuilt DB.

9. **Report** before/after run count, measurement count, and DB size. Then stop and let
   the user review the diff. Do not commit unless asked.

## Rules

- Never hand-edit `shield_data.db`. A hook blocks it.
- Never edit files under `run_data/` to make validation pass — that is experimental
  data. If it is malformed, report it; the fix belongs upstream in `SHIELD_DAS`.
