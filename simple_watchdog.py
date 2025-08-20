from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import subprocess
import time
from datetime import datetime
from pathlib import Path

# Configuration
WATCH_FOLDER = "results"
REPO_ROOT = Path(__file__).parent
BASE_BRANCH = "main"


class FileHandler(FileSystemEventHandler):
    def __init__(self):
        self.file_branches = {}  # Track which branch each file uses
        
    def on_any_event(self, event):
        if event.is_directory:
            return
            
        # Handle all file events (created, modified, moved)
        if event.event_type in ['created', 'moved']:
            file_path = Path(event.dest_path if event.event_type == 'moved' else event.src_path)
            print(f"New file detected: {file_path.name}")
            self.process_file(file_path, is_new=True)
            
        elif event.event_type == 'modified':
            file_path = Path(event.src_path)
            print(f"File modified: {file_path.name}")
            self.process_file(file_path, is_new=False)

    def process_file(self, file_path, is_new=True):
        """Process a file by creating/updating a branch and PR"""
        file_name = file_path.name
        
        # Create branch name based on file name (remove special characters)
        safe_name = "".join(c for c in file_name if c.isalnum() or c in ".-_").replace(".", "-")
        branch_name = f"add-{safe_name}"
        
        try:
            if is_new:
                # New file: create new branch and PR
                self.create_new_file_branch(file_path, branch_name)
                self.file_branches[file_name] = branch_name
            else:
                # Modified file: update existing branch
                if file_name in self.file_branches:
                    self.update_existing_file(file_path, self.file_branches[file_name])
                else:
                    # File was modified but we don't have a branch (maybe script was restarted)
                    print(f"No tracked branch for {file_name}, creating new one...")
                    self.create_new_file_branch(file_path, branch_name)
                    self.file_branches[file_name] = branch_name
                    
        except Exception as e:
            print(f"Error processing {file_name}: {e}")

    def create_new_file_branch(self, file_path, branch_name):
        """Create a new branch for a new file"""
        print(f"Creating new branch: {branch_name}")
        
        # Switch to main and pull latest
        self.run_git(["checkout", BASE_BRANCH])
        self.run_git(["pull", "origin", BASE_BRANCH], check=False)
        
        # Create and switch to new branch
        self.run_git(["checkout", "-b", branch_name])
        
        # Add and commit the file
        relative_path = file_path.relative_to(REPO_ROOT)
        self.run_git(["add", str(relative_path)])
        
        commit_message = f"Add {file_path.name}"
        self.run_git(["commit", "-m", commit_message])
        
        # Push the branch
        self.run_git(["push", "origin", branch_name])
        
        # Create PR
        self.create_pr(file_path.name, branch_name, commit_message)

    def update_existing_file(self, file_path, branch_name):
        """Update an existing file in its branch"""
        print(f"Updating existing file in branch: {branch_name}")
        
        # Switch to the file's branch
        self.run_git(["checkout", branch_name])
        
        # Add and commit the changes
        relative_path = file_path.relative_to(REPO_ROOT)
        self.run_git(["add", str(relative_path)])
        
        # Check if there are changes to commit
        result = self.run_git(["diff", "--cached", "--quiet"], check=False)
        if result.returncode == 0:
            print("No changes to commit")
            return
        
        commit_message = f"Update {file_path.name} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        self.run_git(["commit", "-m", commit_message])
        
        # Push the changes
        self.run_git(["push", "origin", branch_name])
        print(f"✅ Pushed update to {file_path.name}")

    def run_git(self, cmd, check=True):
        """Run a git command"""
        full_cmd = ["git"] + cmd
        result = subprocess.run(
            full_cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0 and check:
            print(f"Git command failed: {' '.join(full_cmd)}")
            print(f"Error: {result.stderr}")
            print(f"Output: {result.stdout}")
            raise subprocess.CalledProcessError(result.returncode, full_cmd, result.stdout, result.stderr)
        
        return result

    def create_pr(self, file_name, branch_name, commit_message):
        """Create a GitHub PR"""
        try:
            # Check if PR already exists
            result = subprocess.run(
                ["gh", "pr", "list", "--head", branch_name, "--json", "number"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0 and result.stdout.strip() != "[]":
                print(f"PR already exists for branch {branch_name}")
                return
            
            # Create new PR
            pr_title = f"Add/Update: {file_name}"
            pr_body = f"""## File: `{WATCH_FOLDER}/{file_name}`

This PR was automatically created when `{file_name}` was added to the `{WATCH_FOLDER}/` directory.

**Initial commit:** {commit_message}
**Created:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

### About this PR:
- ✅ This PR will be automatically updated if the file is modified
- ✅ Each modification will create a new commit in this branch
- ✅ Review the file and merge when ready

---
*This PR was created automatically by the file monitoring system.*
"""
            
            subprocess.run(
                [
                    "gh", "pr", "create",
                    "--title", pr_title,
                    "--body", pr_body,
                    "--base", BASE_BRANCH,
                    "--head", branch_name
                ],
                cwd=REPO_ROOT,
                check=True
            )
            
            print(f"✅ Created PR for {file_name}")
            
        except subprocess.CalledProcessError as e:
            print(f"Failed to create PR: {e}")


def main():
    """Main function to start the file watcher"""
    watch_path = REPO_ROOT / WATCH_FOLDER
    
    # Create watch folder if it doesn't exist
    watch_path.mkdir(exist_ok=True)
    
    print(f"🔍 Monitoring folder: {watch_path}")
    print(f"📂 Repository root: {REPO_ROOT}")
    print(f"🌿 Base branch: {BASE_BRANCH}")
    print("📁 Watching for ANY file changes...")
    print("📝 Each file gets its own branch and PR")
    print("🔄 File modifications will update the existing PR")
    print("Press Ctrl+C to stop\n")
    
    event_handler = FileHandler()
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
