import csv
import json
from pathlib import Path


def build_catalogue(runs_dir: str | Path) -> None:
    """Scan runs_dir/ and write a runs_catalogue.csv and README.md.

    Columns: run_id, path, run_type, date, furnace_setpoint, material, coating
    A run is any directory under runs_dir/ that contains pressure_gauge_data.csv.

    Args:
        runs_dir: Path to the directory containing run folders
    """
    runs_dir = Path(runs_dir).resolve()

    if not runs_dir.exists():
        raise FileNotFoundError(f"Run directory does not exist: {runs_dir}")
    if not runs_dir.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {runs_dir}")

    out_csv = runs_dir / "runs_catalogue.csv"
    cols = [
        "run_id",
        "path",
        "run_type",
        "date",
        "furnace_setpoint",
        "material",
        "coating",
    ]

    def _meta(p: Path) -> dict:
        f = p / "run_metadata.json"
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    rows = []
    if runs_dir.exists():
        for run_path in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
            if not (run_path / "pressure_gauge_data.csv").exists():
                continue
            meta = _meta(run_path)
            run_info = meta.get("run_info", {})
            # Use relative path from runs_dir
            relative_path = run_path.relative_to(runs_dir.parent)
            rows.append(
                {
                    "run_id": run_path.name,
                    "path": relative_path.as_posix(),
                    "run_type": str(run_info.get("run_type", "")),
                    "date": str(run_info.get("date", "")),
                    "furnace_setpoint": str(run_info.get("furnace_setpoint", "")),
                    "material": str(run_info.get("material", "unknown")),
                    "coating": str(run_info.get("coating", "None")),
                }
            )

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    # Generate README.md with the catalogue as a table
    readme_path = runs_dir / "README.md"
    with readme_path.open("w", encoding="utf-8") as f:
        f.write("# Run Data Catalogue\n\n")
        f.write(f"Total runs: {len(rows)}\n\n")

        if rows:
            # Create markdown table header
            f.write(
                "| Run ID | Path | Run Type | Date | "
                "Furnace Setpoint (K) | Material | Coating |\n"
            )
            f.write(
                "|--------|------|----------|------|"
                "----------------------|----------|----------|\n"
            )

            # Write each row
            for row in rows:
                f.write(
                    f"| {row['run_id']} | "
                    f"{row['path']} | "
                    f"{row['run_type']} | "
                    f"{row['date']} | "
                    f"{row['furnace_setpoint']} | "
                    f"{row['material']} | "
                    f"{row['coating']} |\n"
                )
        else:
            f.write("No runs found.\n")
