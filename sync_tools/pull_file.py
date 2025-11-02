#!/usr/bin/env python3
"""
pull_file.py — fetch and overwrite a single file from remote branch
Usage: python pull_file.py path/to/file
"""
import subprocess, sys, os

def run(cmd):
    return subprocess.run(cmd, check=True, text=True)

if len(sys.argv) < 2:
    print("Usage: python pull_file.py <path/to/file>")
    sys.exit(1)

file_path = sys.argv[1]
# quick check for git repo
if not os.path.isdir(".git"):
    sys.exit("Not a git repository (no .git found). Run from repo root.")

branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()

print(f"Fetching origin/{branch}...")
run(["git", "fetch", "origin", branch])

print(f"Checking out {file_path} from origin/{branch} (will overwrite local file)...")
res = subprocess.run(["git", "checkout", f"origin/{branch}", "--", file_path])
if res.returncode != 0:
    sys.exit(f"Failed to checkout {file_path} from origin/{branch}")

print(f"✅ Updated {file_path} from origin/{branch}.")
print("Tip: stage & commit if you want this change recorded locally.")
