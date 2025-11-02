#!/usr/bin/env python3
"""
push_repo.py — commit all changes (if any) and push current branch
Supports optional --rebase flag to fetch+rebase before pushing.
Usage:
    python push_repo.py [--rebase]
"""
import subprocess, sys

def run(cmd):
    return subprocess.run(cmd, check=True, text=True)

rebase = "--rebase" in sys.argv

branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()

if rebase:
    print(f"Fetching origin/{branch} and rebasing local {branch} on it...")
    run(["git", "fetch", "origin", branch])
    # attempt rebase; if it fails, user must resolve
    rc = subprocess.run(["git", "rebase", f"origin/{branch}"]).returncode
    if rc != 0:
        print("Rebase failed. Resolve conflicts manually (git rebase --continue) and then run this script again.")
        sys.exit(2)

run(["git", "add", "-A"])
diff_exit = subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode
if diff_exit == 0:
    print(f"No changes to commit. Pushing branch {branch}.")
else:
    run(["git", "commit", "-m", "sync: repo update"])

# Normal push; if remote has diverged this will be rejected (no force)
try:
    run(["git", "push", "origin", branch])
except subprocess.CalledProcessError:
    print("Push rejected (remote has changes). Consider running with --rebase or merge the remote changes locally.")
    sys.exit(1)

print("✅ Repository pushed successfully.")
