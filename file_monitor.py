"""
GitHub Watchdog - Automated File Monitoring and PR Creation

This script monitors a specified folder for file changes and automatically:
1. Creates a new branch and PR for each new file
2. Updates existing PRs when files are modified
3. Uses file-specific branch naming for organization

Usage: python watchdog.py
Press Ctrl+C to stop monitoring
"""

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import subprocess
import time
from datetime import datetime
from pathlib import Path

# Configuration
WATCH_FOLDER = "results"  # Folder to monitor
REPO_ROOT = Path(__file__).parent  # Repository root directory
BASE_BRANCH = "main"  # Base branch for PRs
GITHUB_CLI_PATH = r"C:\Program Files\GitHub CLI\gh.exe"  # Full path to GitHub CLI


class FileWatchdogHandler(FileSystemEventHandler):
    def __init__(self):
        self.file_branches = {}  # Track which files belong to which branches
        print(f"📋 File tracking initialized")

    def on_any_event(self, event):
        """Handle all file system events"""
        if event.is_directory:
            return

        print(f"🔍 Event: {event.event_type} - {Path(event.src_path).name}")

        if event.event_type in ['created', 'moved']:
            # New file detected
            file_path = Path(event.dest_path if event.event_type == 'moved' else event.src_path)
            self.handle_new_file(file_path)

        elif event.event_type == 'modified':
            # File modification detected
            file_path = Path(event.src_path)
            self.handle_file_update(file_path)

    def handle_new_file(self, file_path):
        """Process a newly created or moved file"""
        file_name = file_path.name
        print(f"📁 Processing new file: {file_name}")

        # Create branch name from filename (sanitize special characters)
        safe_name = "".join(c for c in file_name if c.isalnum() or c in ".-_").replace(".", "-")
        branch_name = f"add-{safe_name}"

        # Store the file-to-branch mapping
        self.file_branches[file_name] = branch_name

        # Execute git workflow
        commit_message = f"Add {file_name} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        try:
            self.create_new_branch_and_pr(file_name, branch_name, commit_message)
        except Exception as e:
            print(f"❌ Error processing new file {file_name}: {e}")

    def handle_file_update(self, file_path):
        """Process a file modification"""
        file_name = file_path.name
        print(f"✏️  Processing file update: {file_name}")

        # Check if we're tracking this file
        if file_name in self.file_branches:
            branch_name = self.file_branches[file_name]
            self.update_existing_branch(file_name, branch_name)
        else:
            # File was modified but we don't have a branch (maybe script was restarted)
            print(f"🔄 No tracked branch for {file_name}, treating as new file...")
            self.handle_new_file(file_path)

    def create_new_branch_and_pr(self, file_name, branch_name, commit_message):
        """Create a new branch and PR for a new file"""
        print(f"🌿 Creating new branch: {branch_name}")

        # Step 1: Switch to main branch
        print("1️⃣  Switching to main...")
        self.run_git(["checkout", BASE_BRANCH])

        # Step 2: Create and switch to new branch (delete if exists)
        print(f"2️⃣  Creating branch {branch_name}...")
        self.run_git(["branch", "-D", branch_name], check=False)  # Delete if exists
        self.run_git(["checkout", "-b", branch_name])

        # Step 3: Add all changes
        print("3️⃣  Adding files...")
        self.run_git(["add", "."])

        # Step 4: Commit changes
        print("4️⃣  Committing...")
        self.run_git(["commit", "-m", commit_message])

        # Step 5: Push branch
        print("5️⃣  Pushing to GitHub...")
        self.run_git(["push", "origin", branch_name])

        # Step 6: Create PR
        print("6️⃣  Creating pull request...")
        self.create_pull_request(file_name, branch_name)

        print(f"✅ Successfully processed {file_name}")

    def update_existing_branch(self, file_name, branch_name):
        """Update an existing branch with file modifications"""
        print(f"🔄 Updating existing branch: {branch_name}")

        commit_message = f"Update {file_name} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        try:
            # Step 1: Switch to the file's branch
            print(f"1️⃣  Switching to branch {branch_name}...")
            self.run_git(["checkout", branch_name])

            # Step 2: Add the specific file
            print("2️⃣  Adding changes...")
            self.run_git(["add", f"{WATCH_FOLDER}/{file_name}"])

            # Step 3: Check if there are changes to commit
            result = self.run_git(["diff", "--cached", "--quiet"], check=False)
            if result.returncode == 0:
                print("ℹ️  No changes to commit")
                return

            # Step 4: Commit the update
            print("3️⃣  Committing update...")
            self.run_git(["commit", "-m", commit_message])

            # Step 5: Push the update
            print("4️⃣  Pushing update...")
            self.run_git(["push", "origin", branch_name])

            print(f"✅ Successfully updated {file_name} in existing PR")

        except Exception as e:
            print(f"❌ Update error for {file_name}: {e}")

    def run_git(self, cmd, check=True):
        """Execute a git command with error handling"""
        full_cmd = ["git"] + cmd
        result = subprocess.run(
            full_cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode != 0 and check:
            print(f"💥 Git command failed: {' '.join(full_cmd)}")
            print(f"   Error: {result.stderr.strip()}")
            raise subprocess.CalledProcessError(result.returncode, full_cmd, result.stdout, result.stderr)

        return result

    def create_pull_request(self, file_name, branch_name):
        """Create a GitHub pull request using GitHub CLI"""
        try:
            # Check if PR already exists for this branch
            result = subprocess.run(
                [GITHUB_CLI_PATH, "pr", "list", "--head", branch_name, "--json", "number"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode == 0 and result.stdout.strip() != "[]":
                print(f"ℹ️  PR already exists for branch {branch_name}")
                return

            # Create new PR
            pr_title = f"Add: {file_name}"
            pr_body = f"""## 📁 New File: `{WATCH_FOLDER}/{file_name}`

This PR was automatically created when `{file_name}` was added to the `{WATCH_FOLDER}/` directory.

### 🤖 Automated Features:
- ✅ **Auto-updates**: This PR will be automatically updated if the file is modified
- ✅ **Timestamped commits**: Each modification creates a new timestamped commit
- ✅ **Ready for review**: Review the file and merge when ready

**Created:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---
*This PR was created automatically by the File Watchdog system.*
"""

            subprocess.run(
                [
                    GITHUB_CLI_PATH, "pr", "create",
                    "--title", pr_title,
                    "--body", pr_body,
                    "--base", BASE_BRANCH,
                    "--head", branch_name
                ],
                cwd=REPO_ROOT,
                check=True
            )

            print(f"🎉 Created PR for {file_name}")

        except subprocess.CalledProcessError as e:
            print(f"💥 Failed to create PR: {e}")
            print("💡 Make sure GitHub CLI is authenticated: run 'gh auth login'")


def main():
    """Main function to start the file monitoring system"""
    watch_path = REPO_ROOT / WATCH_FOLDER

    # Create watch folder if it doesn't exist
    watch_path.mkdir(exist_ok=True)

    # Display startup information
    print("🔍 GitHub File Watchdog Starting...")
    print("=" * 50)
    print(f"📂 Repository: {REPO_ROOT}")
    print(f"👀 Monitoring: {watch_path}")
    print(f"🌿 Base branch: {BASE_BRANCH}")
    print(f"🎯 Features:")
    print(f"   • Auto-create PR for new files")
    print(f"   • Auto-update PR when files change")
    print(f"   • File-specific branch naming")
    print("=" * 50)
    print("🚀 Ready! Add files to the monitored folder...")
    print("⏹️  Press Ctrl+C to stop\n")

    # Initialize and start the file watcher
    event_handler = FileWatchdogHandler()
    observer = Observer()
    observer.schedule(event_handler, str(watch_path), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping File Watchdog...")
        observer.stop()

    observer.join()
    print("✅ File Watchdog stopped successfully")


if __name__ == "__main__":
    main()
