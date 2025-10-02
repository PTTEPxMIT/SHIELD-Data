from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import subprocess
import time
from datetime import datetime


class Handler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        name = event.src_path.split("\\")[-1]
        branch = f"add-{name.replace('.', '-')}"
        msg = f"Add {name} - {datetime.now():%Y-%m-%d %H:%M}"

        subprocess.run(
            f'git checkout main && git checkout -b {branch} && git add . && git commit -m "{msg}" && git push origin {branch}',
            shell=True,
        )
        subprocess.run(
            f'gh pr create --title "Add {name}" --body "Auto-added {name}" --base main --head {branch}',
            shell=True,
        )


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
