#!/usr/bin/env python3
"""
pull_repo.py — reset local branch to match remote (destructive)
Usage: python pull_repo.py
"""
import subprocess, sys

def run(cmd):
    return subprocess.run(cmd, check=True, text=True)

branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()

print(f"WARNING: This will reset local '{branch}' to match origin/{branch} and DISCARD local changes.")
confirm = input("Type 'yes' to continue: ").strip().lower()
if confirm != "yes":
    print("Aborted.")
    sys.exit(0)

print(f"Fetching origin/{branch}...")
run(["git", "fetch", "origin", branch])
print(f"Resetting local {branch} to origin/{branch} ...")
run(["git", "reset", "--hard", f"origin/{branch}"])
print(f"✅ Local {branch} now matches origin/{branch}.")
