#!/usr/bin/env python3
"""
push_file.py — stage, commit and push a single file
Usage: python push_file.py path/to/file
"""
import subprocess, sys, os

def run(cmd):
    return subprocess.run(cmd, check=True, text=True)

if len(sys.argv) < 2:
    print("Usage: python push_file.py <path/to/file>")
    sys.exit(1)

file_path = sys.argv[1]
if not os.path.isfile(file_path):
    sys.exit(f"File not found: {file_path}")

branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()

# Stage the file
run(["git", "add", file_path])

# If there's something staged, commit it; otherwise just push branch
diff_exit = subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode
if diff_exit == 0:
    print(f"No staged changes for {file_path}. Pushing branch {branch}.")
else:
    run(["git", "commit", "-m", f"sync: update {file_path}"])

run(["git", "push", "origin", branch])
print("✅ File pushed successfully.")
