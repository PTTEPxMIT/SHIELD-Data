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
from jinja2 import Template

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
        # Find metadata file first
        metadata_path = None
        for file_path in file_paths:
            if "run_metadata.json" in file_path:
                metadata_path = Path("results") / file_path
                break

        if metadata_path is None:
            raise FileNotFoundError("run_metadata.json not found in the added files")

        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadata file does not exist: {metadata_path}")

        # Read metadata
        try:
            with open(metadata_path, "r") as f:
                metadata = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in metadata file: {e}")

        # Validate required metadata fields
        if "run_info" not in metadata:
            raise KeyError("'run_info' section missing from metadata")

        run_info = metadata["run_info"]
        required_fields = ["run_type", "date", "furnace_setpoint"]

        for field in required_fields:
            if field not in run_info:
                raise KeyError(f"Required field '{field}' missing from run_info")

        # Parse folder structure
        sample_path = Path(next(iter(file_paths)))
        path_parts = sample_path.parts

        date_folder = None
        run_folder = None

        for part in path_parts:
            if re.match(r"\d{2}\.\d{2}", part):
                date_folder = part
            elif re.match(r"run_\d+_\d{2}h\d{2}", part):
                run_folder = part

        if not date_folder:
            raise ValueError("Date folder (MM.DD format) not found in path structure")
        if not run_folder:
            raise ValueError(
                "Run folder (run_X_HHhMM format) not found in path structure"
            )

        return {
            "date_folder": date_folder,
            "run_folder": run_folder,
            "metadata": metadata,
            "total_files": len(file_paths),
        }

    def create_pr_content(self, run_info):
        """Create PR title and body based on run information"""
        metadata = run_info["metadata"]
        run_data = metadata["run_info"]

        # Build title
        title = f"New run data: {run_data['run_type']}; {run_data['date']}; {run_data['furnace_setpoint']} K"

        # Load and render template
        template_path = Path("pr_template.md")
        if not template_path.exists():
            raise FileNotFoundError("pr_template.md not found")

        with open(template_path, "r") as f:
            template_content = f.read()

        template = Template(template_content)
        body = template.render(
            run_type=run_data["run_type"],
            date=run_data["date"],
            furnace_setpoint=run_data["furnace_setpoint"],
            total_files=run_info["total_files"],
            metadata_json=json.dumps(metadata, indent=2),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        return title, body

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
                import tempfile

                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".md", delete=False
                ) as f:
                    f.write(body)
                    body_file = f.name

                try:
                    subprocess.run(
                        [
                            "gh",
                            "pr",
                            "create",
                            "--title",
                            title,
                            "--body-file",
                            body_file,
                            "--base",
                            "main",
                            "--head",
                            self.current_branch,
                        ],
                        check=True,
                    )
                finally:
                    import os

                    os.unlink(body_file)

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
