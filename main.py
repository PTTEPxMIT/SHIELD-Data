from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import subprocess
import time
import random
import string
import threading
import json
import re
from datetime import datetime
from pathlib import Path

# Configuration
CHECK_INTERVAL = 10  # How often to check for changes (in seconds)
BATCH_DELAY = 3  # Wait 3 seconds after last event before processing (to batch multiple file changes)


class Handler(FileSystemEventHandler):
    def __init__(self):
        self.current_branch = None
        self.pending_changes = set()
        self.timer = None
        self.session_files = set()  # Track files in current session

    def parse_run_info(self, file_paths):
        """Extract run information from folder structure and metadata"""
        # Find the first file to analyze structure
        sample_path = next(iter(file_paths))
        path_parts = Path(sample_path).parts

        # Extract date (MM.DD) and run info (run_X_HHhMM)
        date_folder = None
        run_folder = None

        for part in path_parts:
            if re.match(r"\d{2}\.\d{2}", part):  # MM.DD format
                date_folder = part
            elif re.match(r"run_\d+_\d{2}h\d{2}", part):  # run_X_HHhMM format
                run_folder = part

        # Try to read metadata
        metadata = {}
        metadata_path = None
        for file_path in file_paths:
            if "run_metadata.json" in file_path:
                metadata_path = Path("results") / file_path
                break

        if metadata_path and metadata_path.exists():
            try:
                with open(metadata_path, "r") as f:
                    metadata = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                print(f"⚠️  Could not read metadata: {e}")

        return {
            "date_folder": date_folder,
            "run_folder": run_folder,
            "metadata": metadata,
            "total_files": len(file_paths),
        }

    def create_pr_content(self, run_info):
        """Create PR title and body based on run information"""
        date_folder = run_info["date_folder"]
        run_folder = run_info["run_folder"]
        metadata = run_info["metadata"]
        total_files = run_info["total_files"]

        # Extract run number and time from folder name
        run_match = re.match(r"run_(\d+)_(\d{2})h(\d{2})", run_folder or "")
        run_number = run_match.group(1) if run_match else "Unknown"
        run_time = (
            f"{run_match.group(2)}:{run_match.group(3)}" if run_match else "Unknown"
        )

        # Build title using metadata fields
        run_type = metadata.get("run_type", "Unknown")
        furnace_setpoint = metadata.get("furnace_setpoint", "Unknown")
        title = f"New run data: {run_type}; {date_folder}; {furnace_setpoint} K"

        # Build detailed body
        body_parts = [
            "## 🔬 Experimental Run Data",
            "",
            f"**Date:** {date_folder}",
            f"**Run Number:** {run_number}",
            f"**Start Time:** {run_time}",
            f"**Total Files:** {total_files}",
            "",
        ]

        # Add metadata information if available
        if metadata:
            body_parts.extend(["### 📊 Run Metadata:", "```json"])
            # Add key metadata fields
            for key, value in metadata.items():
                if isinstance(value, (str, int, float, bool)):
                    body_parts.append(f"{key}: {value}")
            body_parts.append("```")
            body_parts.append("")

        # Add file structure info
        body_parts.extend(
            [
                "### 📁 Data Structure:",
                "- `pressure_gauge_data.csv` - Main experimental data",
                "- `run_metadata.json` - Run configuration and metadata",
                "- `backup/` - Backup data files",
                "",
                "---",
                f"*Auto-generated from experimental run at {datetime.now():%Y-%m-%d %H:%M:%S}*",
            ]
        )

        return title, "\n".join(body_parts)

    def on_any_event(self, event):
        if event.is_directory:
            return

        # Get relative path from results folder
        full_path = Path(event.src_path)
        rel_path = full_path.relative_to(Path("results"))

        print(f"🔍 Detected: {event.event_type} - {rel_path}")

        # Add to pending changes
        self.pending_changes.add(str(rel_path))

        # Cancel existing timer and start new one (batching)
        if self.timer:
            self.timer.cancel()

        self.timer = threading.Timer(BATCH_DELAY, self.process_batch)
        self.timer.start()

    def process_batch(self):
        """Process all pending changes as a batch"""
        if not self.pending_changes:
            return

        print(f"📦 Processing batch of {len(self.pending_changes)} changes...")

        # Parse run information from folder structure and metadata
        run_info = self.parse_run_info(self.pending_changes)
        title, body = self.create_pr_content(run_info)

        # If this is a new session (no current branch), create one
        if not self.current_branch:
            unique_id = "".join(
                random.choices(string.ascii_lowercase + string.digits, k=7)
            )
            self.current_branch = f"add_new_data_{unique_id}"

            # Create branch and initial commit
            date_folder = run_info["date_folder"] or "unknown"
            run_folder = run_info["run_folder"] or "unknown"
            msg = f"Add experimental data: {date_folder}/{run_folder}"

            subprocess.run("git checkout main", shell=True)
            subprocess.run(f"git checkout -b {self.current_branch}", shell=True)
            subprocess.run("git add .", shell=True)

            # Check if there are actually changes to commit
            result = subprocess.run("git diff --cached --quiet", shell=True)
            if result.returncode != 0:  # There are changes
                subprocess.run(f'git commit -m "{msg}"', shell=True)
                subprocess.run(f"git push origin {self.current_branch}", shell=True)

                # Create PR with enhanced title and body
                subprocess.run(
                    [
                        "gh",
                        "pr",
                        "create",
                        "--title",
                        title,
                        "--body",
                        body,
                        "--base",
                        "main",
                        "--head",
                        self.current_branch,
                    ],
                    shell=True,
                )

                print(f"✅ Created branch {self.current_branch} and PR: {title}")
            else:
                print("ℹ️  No changes to commit")
        else:
            # Update existing branch
            msg = f"Update data session - {datetime.now():%Y-%m-%d %H:%M:%S}"

            subprocess.run(f"git checkout {self.current_branch}", shell=True)
            subprocess.run("git add .", shell=True)

            # Check if there are changes
            result = subprocess.run("git diff --cached --quiet", shell=True)
            if result.returncode != 0:  # There are changes
                subprocess.run(f'git commit -m "{msg}"', shell=True)
                subprocess.run(f"git push origin {self.current_branch}", shell=True)
                print(
                    f"🔄 Updated {self.current_branch} with {len(self.pending_changes)} changes"
                )
            else:
                print("ℹ️  No changes to commit")

        # Update session files and clear pending
        self.session_files.update(self.pending_changes)
        self.pending_changes.clear()


observer = Observer()
observer.schedule(Handler(), "results", recursive=True)
observer.start()
print(
    f"Monitoring results/ folder (checking every {CHECK_INTERVAL}s). Press Ctrl+C to stop..."
)
try:
    while True:
        time.sleep(CHECK_INTERVAL)
except KeyboardInterrupt:
    observer.stop()
observer.join()
