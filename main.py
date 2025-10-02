from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import subprocess
import time
import random
import string
from datetime import datetime


class Handler(FileSystemEventHandler):
    def __init__(self):
        self.branches = {}  # Track which files belong to which branches

    def on_created(self, event):
        if event.is_directory:
            return
        name = event.src_path.split("\\")[-1]
        # Generate unique branch name with random alphanumeric suffix
        unique_id = "".join(random.choices(string.ascii_lowercase + string.digits, k=7))
        branch = f"add_new_data_{unique_id}"
        self.branches[name] = branch  # Remember this file's branch
        msg = f"Add {name} - {datetime.now():%Y-%m-%d %H:%M}"

        subprocess.run(
            f'git checkout main && git checkout -b {branch} && git add . && git commit -m "{msg}" && git push origin {branch}',
            shell=True,
        )
        subprocess.run(
            f'gh pr create --title "Add {name}" --body "Auto-added {name}" --base main --head {branch}',
            shell=True,
        )
        print(f"✅ Created branch {branch} and PR for {name}")

    def on_modified(self, event):
        if event.is_directory:
            return
        name = event.src_path.split("\\")[-1]

        if name in self.branches:
            branch = self.branches[name]
            msg = f"Update {name} - {datetime.now():%Y-%m-%d %H:%M:%S}"

            subprocess.run(
                f'git checkout {branch} && git add results/{name} && git commit -m "{msg}" && git push origin {branch}',
                shell=True,
            )
            print(f"🔄 Updated {name} in branch {branch}")
        else:
            print(f"ℹ️  File {name} modified but no branch tracked (treating as new)")


observer = Observer()
observer.schedule(Handler(), "results", recursive=True)
observer.start()
print("Monitoring results/ folder. Press Ctrl+C to stop...")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    observer.stop()
observer.join()
