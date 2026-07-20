---
description: Start a new piece of work on a clean feature branch, or finish one by
  opening a pull request. Use when the user wants to begin a feature/fix, says they
  are about to change code or data, or asks to open a PR for the current branch.
disable-model-invocation: true
argument-hint: [short-topic-description]
---

## Current state

- Branch: !`git branch --show-current`
- Status: !`git status --short`
- Unpushed: !`git log --oneline @{u}.. 2>/dev/null || echo "(no upstream set)"`

## What to do

Read the state above and pick the matching case. `$ARGUMENTS` is the topic, if given.

### Case 1 — on `main`

Starting fresh work.

1. If the working tree is dirty, stop and ask what to do with the changes. Do not
   stash or discard without being told to.
2. `git pull` to get a current `main`.
3. `git switch -c cw/<topic>` — kebab-case, derived from `$ARGUMENTS` or from what the
   user described. Keep it short.
4. Confirm the new branch, then proceed with the actual work.

### Case 2 — on a feature branch with uncommitted or unpushed work

Continuing or wrapping up.

1. Run `ruff format .` then `pytest test/`. Both must be clean before going further.
   If tests fail, report the failure and stop — do not open a PR over red tests.
2. If `run_data/` changed, verify `src/shield_data/shield_data.db` was rebuilt and is
   staged in the same commit. CI rejects data without a rebuilt DB.
3. Commit with a subject line that says what changed and why, not just what file moved.
4. `git push -u origin <branch>`.
5. Open the PR with the correct template:
   - code changes → `gh pr create --template code_change.md`
   - new run data → `gh pr create --template data_addition.md`

   Fill in the template body properly — the checklists exist so the reviewer knows what
   was actually verified. Do not tick a box for something that was not done.
6. Report the PR URL and the status of the `lint` and `run-tests` checks.

### Case 3 — on a feature branch, everything pushed, PR already open

Report the PR status (`gh pr checks`) and ask what the user wants next. Do not merge
unless explicitly asked.

## Rules

- Never commit or push on `main`. A hook enforces this; do not try to route around it.
- Never use `--force`, `--no-verify`, or `git rebase` here.
- Do not merge a PR unless the user explicitly asks for it.
