#!/bin/bash
# Blocks `git commit` / `git push` while on a protected branch.
# Exit 2 = blocking error; stderr is fed back to Claude as feedback.

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty')

# Only care about commit/push. Matches inside compound commands too.
printf '%s' "$CMD" | grep -Eq 'git[[:space:]]+(commit|push)' || exit 0

# `git branch --show-current` is used over `rev-parse --abbrev-ref HEAD`: the latter
# fails and echoes the literal "HEAD" on an unborn branch, silently failing open.
# Empty output means detached HEAD, which is not main — allow it.
BRANCH=$(git branch --show-current 2>/dev/null)
case "$BRANCH" in
  main|master)
    cat >&2 <<EOF
Blocked: refusing to run git commit/push on '$BRANCH'.

This repo requires all work to go through a pull request. Create a branch first:

  git switch -c cw/<topic>

then commit, push with -u, and open a PR (see the /new-feature skill).
EOF
    exit 2
    ;;
esac

exit 0
