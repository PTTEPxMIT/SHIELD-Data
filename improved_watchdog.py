import subprocess
import time
from datetime import datetime
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configuration
WATCH_FOLDER = "results"  # Folder to monitor (relative to repo root)
REPO_ROOT = Path(__file__).parent  # Repository root directory
BRANCH_NAME = "auto-csv-update"
BASE_BRANCH = "main"


class CSVFileHandler(FileSystemEventHandler):
    def __init__(self):
        self.processed_files = set()  # Track processed files to avoid duplicates

    def on_created(self, event):
        """Handle file creation events"""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Only process CSV files
        if file_path.suffix.lower() == ".csv":
            print(f"New CSV file detected: {file_path.name}")
            self.process_csv_file(file_path)

    def on_moved(self, event):
        """Handle file move events (like drag-and-drop)"""
        if event.is_directory:
            return

        dest_path = Path(event.dest_path)

        # Only process CSV files
        if dest_path.suffix.lower() == ".csv":
            print(f"CSV file moved to watched folder: {dest_path.name}")
            self.process_csv_file(dest_path)

    def process_csv_file(self, file_path):
        """Process a new CSV file by creating a PR"""
        file_name = file_path.name

        # Avoid processing the same file multiple times
        if file_name in self.processed_files:
            print(f"File {file_name} already processed, skipping...")
            return

        self.processed_files.add(file_name)

        try:
            # Create and switch to feature branch
            self.ensure_branch_exists()

            # Add the specific CSV file
            relative_path = file_path.relative_to(REPO_ROOT)
            self.run_git_command(["add", str(relative_path)])

            # Check if there are changes to commit
            result = self.run_git_command(["diff", "--cached", "--quiet"], check=False)
            if result.returncode == 0:
                print("No changes to commit")
                return

            # Commit the changes
            commit_message = f"Add new CSV data file: {file_name}"
            self.run_git_command(["commit", "-m", commit_message])

            # Push the branch
            self.run_git_command(["push", "origin", BRANCH_NAME, "--set-upstream"])

            # Create PR if it doesn't exist
            self.create_pull_request(file_name)

        except subprocess.CalledProcessError as e:
            print(f"Git operation failed: {e}")
        except Exception as e:
            print(f"Error processing file {file_name}: {e}")

    def ensure_branch_exists(self):
        """Ensure the feature branch exists and switch to it"""
        try:
            # Check if branch exists locally
            result = self.run_git_command(
                ["branch", "--list", BRANCH_NAME], check=False
            )

            if BRANCH_NAME not in result.stdout:
                # Branch doesn't exist, create it from main
                self.run_git_command(["checkout", "-b", BRANCH_NAME, BASE_BRANCH])
                print(f"Created new branch: {BRANCH_NAME}")
            else:
                # Branch exists, switch to it
                self.run_git_command(["checkout", BRANCH_NAME])
                # Pull latest changes
                self.run_git_command(["pull", "origin", BRANCH_NAME], check=False)
                print(f"Switched to existing branch: {BRANCH_NAME}")

        except subprocess.CalledProcessError:
            # If pull fails, branch might not exist on remote yet
            print(
                f"Branch {BRANCH_NAME} doesn't exist on remote, will be created on push"
            )

    def run_git_command(self, cmd, check=True):
        """Run a git command in the repository root"""
        full_cmd = ["git"] + cmd
        return subprocess.run(
            full_cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=check
        )

    def create_pull_request(self, file_name):
        """Create a GitHub PR using GitHub CLI"""
        try:
            # Check if PR already exists for this branch
            result = subprocess.run(
                ["gh", "pr", "list", "--head", BRANCH_NAME, "--json", "number"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0 and result.stdout.strip() != "[]":
                print(f"PR already exists for branch {BRANCH_NAME}")
                return

            # Create new PR
            pr_title = f"Add new CSV data file: {file_name}"
            pr_body = f"""## New Data File Added

A new CSV data file has been automatically detected and added to the repository:

**File:** `{WATCH_FOLDER}/{file_name}`
**Timestamp:** {datetime.now().isoformat()}

This PR was created automatically by the data monitoring system.

### Next Steps
- [ ] Review the data file for quality and completeness
- [ ] Verify the data format is correct
- [ ] Add any necessary documentation or metadata
- [ ] Merge when ready
"""

            subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--title",
                    pr_title,
                    "--body",
                    pr_body,
                    "--base",
                    BASE_BRANCH,
                    "--head",
                    BRANCH_NAME,
                ],
                cwd=REPO_ROOT,
                check=True,
            )

            print(f"✅ Created PR for {file_name}")

        except subprocess.CalledProcessError as e:
            print(f"Failed to create PR: {e}")
            # Check if it's because gh CLI is not authenticated
            if "authentication" in str(e).lower():
                print("💡 Make sure GitHub CLI is authenticated: run 'gh auth login'")


def main():
    """Main function to start the file watcher"""
    watch_path = REPO_ROOT / WATCH_FOLDER

    # Create watch folder if it doesn't exist
    watch_path.mkdir(exist_ok=True)

    print(f"🔍 Monitoring folder: {watch_path}")
    print(f"📂 Repository root: {REPO_ROOT}")
    print(f"🌿 Target branch: {BRANCH_NAME}")
    print("📁 Watching for new CSV files...")
    print("Press Ctrl+C to stop\n")

    event_handler = CSVFileHandler()
    observer = Observer()
    observer.schedule(event_handler, str(watch_path), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping file watcher...")
        observer.stop()

    observer.join()
    print("✅ File watcher stopped")


if __name__ == "__main__":
    main()
