from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import subprocess
import time
from datetime import datetime

REPO_PATH = "."  # Current directory (repo root)
WATCH_FOLDER = "results"


class SimpleFileHandler(FileSystemEventHandler):
    def on_any_event(self, event):
        if event.is_directory:
            return
        
        print(f"Event: {event.event_type} - {event.src_path}")
        
        if event.event_type in ['created', 'moved']:
            file_name = event.dest_path if event.event_type == 'moved' else event.src_path
            file_name = file_name.split('\\')[-1]  # Get just the filename
            
            print(f"Processing new file: {file_name}")
            
            # Create branch name from filename
            safe_name = "".join(c for c in file_name if c.isalnum() or c in ".-_").replace(".", "-")
            branch_name = f"add-{safe_name}"
            
            # Simple git workflow
            commit_message = f"Add {file_name} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            try:
                print(f"1. Switching to main...")
                subprocess.run(["git", "checkout", "main"], cwd=REPO_PATH, check=True)
                
                print(f"2. Creating branch {branch_name}...")
                # Delete branch if it exists
                subprocess.run(["git", "branch", "-D", branch_name], cwd=REPO_PATH, check=False)
                subprocess.run(["git", "checkout", "-b", branch_name], cwd=REPO_PATH, check=True)
                
                print(f"3. Adding files...")
                subprocess.run(["git", "add", "."], cwd=REPO_PATH, check=True)
                
                print(f"4. Committing...")
                subprocess.run(["git", "commit", "-m", commit_message], cwd=REPO_PATH, check=True)
                
                print(f"5. Pushing...")
                subprocess.run(["git", "push", "origin", branch_name], cwd=REPO_PATH, check=True)
                
                print(f"6. Creating PR...")
                subprocess.run([
                    "gh", "pr", "create",
                    "--title", f"Add {file_name}",
                    "--body", f"Automatically added {file_name}",
                    "--base", "main",
                    "--head", branch_name
                ], cwd=REPO_PATH, check=False)  # Don't fail if PR already exists
                
                print(f"✅ Successfully processed {file_name}")
                
            except subprocess.CalledProcessError as e:
                print(f"❌ Error: {e}")


if __name__ == "__main__":
    print("🔍 Simple File Watcher Starting...")
    print(f"📁 Watching: {WATCH_FOLDER}")
    print("Press Ctrl+C to stop\n")
    
    event_handler = SimpleFileHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_FOLDER, recursive=True)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping...")
        observer.stop()
    
    observer.join()
    print("✅ Stopped")
