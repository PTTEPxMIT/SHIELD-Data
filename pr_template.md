## Experimental Run Data

**Run Type:** {{ run_type }}
**Date:** {{ date }}
**Furnace Setpoint:** {{ furnace_setpoint }} K
**Total Files:** {{ total_files }}

### Run Metadata:
```json
{{ metadata_json }}
```

### Data Structure:
- `pressure_gauge_data.csv` - Main experimental data
- `run_metadata.json` - Run configuration and metadata
- `backup/` - Backup data files

---
*Auto-generated at {{ timestamp }}*