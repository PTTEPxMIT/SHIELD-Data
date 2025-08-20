from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import subprocess
import time
from datetime import datetime

REPO_PATH = "results/"
BRANCH_NAME = "auto-update"


class GitHandler(FileSystemEventHandler):
    def on_any_event(self, event):
        if event.is_directory:
            return
        # Stage, commit, and push changes
        commit_message = f"Auto-update at {datetime.now().isoformat()}"
        subprocess.run(["git", "-C", REPO_PATH, "checkout", BRANCH_NAME], check=True)
        subprocess.run(["git", "-C", REPO_PATH, "add", "."], check=True)
        subprocess.run(
            ["git", "-C", REPO_PATH, "commit", "-m", commit_message], check=False
        )
        subprocess.run(
            ["git", "-C", REPO_PATH, "push", "origin", BRANCH_NAME], check=True
        )

        # Open a PR using GitHub CLI (requires `gh` installed & authenticated)
        subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--title",
                commit_message,
                "--body",
                "Automated change detected and committed",
                "--base",
                "main",
                "--head",
                BRANCH_NAME,
            ],
            cwd=REPO_PATH,
            check=False,
        )


if __name__ == "__main__":
    path = REPO_PATH
    event_handler = GitHandler()
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
