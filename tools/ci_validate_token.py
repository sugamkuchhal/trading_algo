#!/usr/bin/env python3
"""
ci_validate_token.py

Usage:
  python tools/ci_validate_token.py --env saras
  python tools/ci_validate_token.py --env vs

Exits with 0 if token looks valid, else non-zero.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--env", required=True, choices=["saras", "vs"])
    return p.parse_args()

def load_token_file(env):
    path = Path.home() / ".config" / "trading_algo" / f"access_token_{env}.json"
    if not path.exists():
        print(f"No token file at {path}; marking invalid", flush=True)
        return None, path
    try:
        data = json.loads(path.read_text())
        return data, path
    except Exception as e:
        print(f"Failed to read/parse {path}: {e}; marking invalid", flush=True)
        return None, path

def check_expiry(data):
    # If explicit expiry/unix timestamp present — prefer it.
    now = int(time.time())
    candidates = []
    # common fields
    for k in ("expires_at", "expiry", "expiry_ts", "expires_at_ms", "expires_in"):
        if k in data:
            candidates.append((k, data[k]))
    if not candidates:
        return None  # unknown

    for k, v in candidates:
        try:
            if k == "expires_in":
                # seconds from now
                exp = now + int(v)
            elif k.endswith("_ms"):
                exp = int(v) // 1000
            else:
                exp = int(v)
                # if value looks far in future but small, try to detect (heuristic)
                if exp > 10**12:  # clearly ms timestamp
                    exp = exp // 1000
            return exp
        except Exception:
            continue
    return None

def main():
    args = parse_args()
    data, path = load_token_file(args.env)
    if not data:
        sys.exit(1)

    # Basic presence check
    access_token = data.get("access_token") or data.get("token") or data.get("accessToken")
    if not access_token:
        print(f"No access_token found in {path}; marking invalid", flush=True)
        sys.exit(1)

    # If expiry info exists, verify not expired
    expiry_ts = check_expiry(data)
    if expiry_ts is not None:
        now = int(time.time())
        if expiry_ts - now < 60:
            # less than 60s left -> treat as expired
            print(f"Token in {path} appears expired (expiry={expiry_ts}, now={now}); marking invalid", flush=True)
            sys.exit(1)
        else:
            print(f"Token in {path} has expiry={expiry_ts} (now={now}) -> valid", flush=True)
            sys.exit(0)

    # No expiry info — fall back to conservative success if file exists and token is non-empty.
    print(f"Token file {path} exists and access_token present -> treating as valid (no expiry found)", flush=True)
    sys.exit(0)

if __name__ == "__main__":
    main()
