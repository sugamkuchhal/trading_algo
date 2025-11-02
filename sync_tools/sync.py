#!/usr/bin/env python3
"""
sync.py — small runner for sync_tools
Usage:
  python sync.py push-file path/to/file
  python sync.py push-repo [--rebase]
  python sync.py pull-file path/to/file
  python sync.py pull-repo
"""
import sys, subprocess

def call(script, *args):
    cmd = ["python", script] + list(args)
    subprocess.run(cmd, check=True)

if len(sys.argv) < 2:
    print("Usage: python sync.py <push-file|push-repo|pull-file|pull-repo> [args...]")
    sys.exit(1)

cmd = sys.argv[1]
if cmd == "push-file":
    if len(sys.argv) < 3:
        print("Usage: python sync.py push-file <path/to/file>")
        sys.exit(1)
    call("push_file.py", sys.argv[2])
elif cmd == "push-repo":
    extra = []
    if "--rebase" in sys.argv:
        extra.append("--rebase")
    call("push_repo.py", *extra)
elif cmd == "pull-file":
    if len(sys.argv) < 3:
        print("Usage: python sync.py pull-file <path/to/file>")
        sys.exit(1)
    call("pull_file.py", sys.argv[2])
elif cmd == "pull-repo":
    call("pull_repo.py")
else:
    print("Unknown command. See usage.")
    sys.exit(1)
