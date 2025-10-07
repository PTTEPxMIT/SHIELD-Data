from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import subprocess
import time
import random
import string
import threading
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

        # If this is a new session (no current branch), create one
        if not self.current_branch:
            unique_id = "".join(
                random.choices(string.ascii_lowercase + string.digits, k=7)
            )
            self.current_branch = f"add_new_data_{unique_id}"

            # Create branch and initial commit
            msg = f"Add new data session - {datetime.now():%Y-%m-%d %H:%M}"

            subprocess.run("git checkout main", shell=True)
            subprocess.run(f"git checkout -b {self.current_branch}", shell=True)
            subprocess.run("git add .", shell=True)

            # Check if there are actually changes to commit
            result = subprocess.run("git diff --cached --quiet", shell=True)
            if result.returncode != 0:  # There are changes
                subprocess.run(f'git commit -m "{msg}"', shell=True)
                subprocess.run(f"git push origin {self.current_branch}", shell=True)

                # Create PR
                file_list = "\\n".join(f"- {f}" for f in sorted(self.pending_changes))
                subprocess.run(
                    [
                        "gh",
                        "pr",
                        "create",
                        "--title",
                        f"Add new data [{unique_id}]: {len(self.pending_changes)} files",
                        "--body",
                        f"Auto-added data files:\\n\\n{file_list}",
                        "--base",
                        "main",
                        "--head",
                        self.current_branch,
                    ],
                    shell=True,
                )

                print(
                    f"✅ Created branch {self.current_branch} and PR for {len(self.pending_changes)} files"
                )
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
