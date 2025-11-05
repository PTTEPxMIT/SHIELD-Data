import json
import os
import random
import re
import string
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from jinja2 import Template
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .build_catalogue import build_catalogue

# Default configuration
DEFAULT_CHECK_INTERVAL = 10  # How often to check for changes (in seconds)
DEFAULT_BATCH_DELAY = 3  # Wait seconds after last event before processing


class Handler(FileSystemEventHandler):
    """Handler for monitoring file system events and processing data uploads

    Args:
        results_folder: Path to the results folder to monitor
        current_branch: Current git branch for the upload session
        pending_changes: Set of pending file changes to process
        timer: Timer for batching file changes
        session_files: Set of files tracked in the current session

    Attributes:
        results_folder: Path to the results folder to monitor
        current_branch: Current git branch for the upload session
        pending_changes: Set of pending file changes to process
        timer: Timer for batching file changes
        session_files: Set of files tracked in the current session

    """

    results_folder: str
    current_branch: str | None
    pending_changes: set[str]
    timer: threading.Timer | None
    session_files: set[str]
    batch_delay: float

    def __init__(self, results_folder="results", batch_delay=DEFAULT_BATCH_DELAY):
        self.results_folder = results_folder
        self.batch_delay = batch_delay
        self.current_branch = None
        self.pending_changes = set()
        self.timer = None
        self.session_files = set()  # Track files in current session

    def parse_run_info(self, file_paths: set[str]) -> dict:
        """Extract run information from folder structure and metadata"""
        # Parse folder structure from any file in the batch
        sample_path = Path(next(iter(file_paths)))
        path_parts = sample_path.parts

        run_folder = None

        # Look for folder matching YY.MM.DD_run_X_HHhMM format
        for part in path_parts:
            if re.match(r"\d{2}\.\d{2}\.\d{2}_run_\d+_\d{2}h\d{2}", part):
                run_folder = part
                break

        if not run_folder:
            raise ValueError(
                "Run folder (YY.MM.DD_run_X_HHhMM format) not found in path structure"
            )

        # Find metadata file in the run folder (not necessarily in current batch)
        metadata_path = Path(self.results_folder) / run_folder / "run_metadata.json"

        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadata file does not exist: {metadata_path}")

        # Read metadata
        try:
            with open(metadata_path) as f:
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

        return {
            "run_folder": run_folder,
            "metadata": metadata,
            "total_files": len(file_paths),
        }

    def create_pr_content(self, run_info: dict) -> tuple[str, str]:
        """Create PR title and body based on run information"""
        metadata = run_info["metadata"]
        run_data = metadata["run_info"]

        # Build title
        title = (
            f"New run data: {run_data['run_type']}; "
            f"{run_data['date']}; "
            f"{run_data['furnace_setpoint']} K"
        )

        # Load and render template
        template_path = Path(__file__).parent / "pr_template.md"

        with open(template_path) as f:
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

    def on_any_event(self, event: any):
        """Handle any file system event"""
        if event.is_directory:
            return

        # Get relative path from results folder
        full_path = Path(event.src_path)
        rel_path = full_path.relative_to(Path(self.results_folder))

        # Ignore files in backup folder
        if "backup" in rel_path.parts:
            return

        # Ignore catalogue files (they are auto-generated)
        if rel_path.name in ("runs_catalogue.csv", "README.md"):
            return

        print(f"🔍 Detected: {event.event_type} - {rel_path}")

        # Add to pending changes
        self.pending_changes.add(str(rel_path))

        # Cancel existing timer and start new one (batching)
        if self.timer:
            self.timer.cancel()

        self.timer = threading.Timer(self.batch_delay, self.process_batch)
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
            run_folder = run_info["run_folder"] or "unknown"
            msg = f"Add experimental data: {run_folder}"

            subprocess.run("git checkout main", shell=True)
            subprocess.run(f"git checkout -b {self.current_branch}", shell=True)

            # Rebuild catalogue before committing
            print("📊 Rebuilding catalogue...")
            build_catalogue(self.results_folder)

            subprocess.run(f"git add {self.results_folder}/", shell=True)

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
                    os.unlink(body_file)

                print(f"✅ Created branch {self.current_branch} and PR: {title}")
            else:
                print("ℹ️  No changes to commit")  # noqa: RUF001
        else:
            # Update existing branch
            msg = f"Update data session - {datetime.now():%Y-%m-%d %H:%M:%S}"

            subprocess.run(f"git checkout {self.current_branch}", shell=True)

            # Rebuild catalogue before committing
            print("📊 Rebuilding catalogue...")
            build_catalogue(self.results_folder)

            subprocess.run(f"git add {self.results_folder}/", shell=True)

            # Check if there are changes
            result = subprocess.run("git diff --cached --quiet", shell=True)
            if result.returncode != 0:  # There are changes
                subprocess.run(f'git commit -m "{msg}"', shell=True)
                subprocess.run(f"git push origin {self.current_branch}", shell=True)
                print(
                    f"🔄 Updated {self.current_branch} with "
                    f"{len(self.pending_changes)} changes"
                )
            else:
                print("ℹ️  No changes to commit")  # noqa: RUF001

        # Update session files and clear pending
        self.session_files.update(self.pending_changes)
        self.pending_changes.clear()


def upload_data_from_folder(
    results_folder: str,
    check_interval: float = DEFAULT_CHECK_INTERVAL,
    batch_delay: float = DEFAULT_BATCH_DELAY,
):
    """Monitor provided results folder and upload data changes via GitHub PRs

    Args:
        results_folder: Path to the folder to monitor for data changes
        check_interval: How often to check for changes (in seconds). Default: 10
        batch_delay: Wait time after last event before processing batch (in seconds).
                     Must be less than check_interval. Default: 3

    Raises:
        FileNotFoundError: If the results folder doesn't exist
        NotADirectoryError: If the path is not a directory
        ValueError: If batch_delay >= check_interval
    """

    # Check if folder exists
    folder_path = Path(results_folder)
    if not folder_path.exists():
        raise FileNotFoundError(f"Folder does not exist: {results_folder}")
    if not folder_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {results_folder}")

    # Validate timing parameters
    if batch_delay >= check_interval:
        raise ValueError(
            f"batch_delay ({batch_delay}s) must be less than "
            f"check_interval ({check_interval}s)"
        )

    observer = Observer()
    handler = Handler(results_folder, batch_delay)
    observer.schedule(handler, f"{results_folder}", recursive=True)
    observer.start()
    print(
        f"Monitoring {results_folder}/ folder "
        f"(checking every {check_interval}s). "
        "Press Ctrl+C to stop..."
    )
    try:
        while True:
            time.sleep(check_interval)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
