#!/usr/bin/env python3
"""
ci_validate_token.py

Validates whether an access token looks usable *based only on local info*.

- If token file exists and contains a non-empty token → usually valid
- If an expiry timestamp exists → must be in the future
- If expiry is missing → treated as valid (non-strict mode)
- Exits 0 for valid, 1 for invalid (CI uses this to skip Selenium/Chrome)
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


def load_json(path: Path):
    if not path.exists():
        print(f"[validator] ❌ Token file not found: {path}", flush=True)
        return None
    try:
        return json.loads(path.read_text())
    except Exception as e:
        print(f"[validator] ❌ Failed to parse {path}: {e}", flush=True)
        return None


def extract_expiry(data: dict):
    """
    Try to interpret any common expiry fields.
    Returns expiry_ts (int) or None if no usable expiry found.
    """
    now = int(time.time())
    possible_keys = ["expiry", "expires_at", "expiry_ts", "expires_at_ms", "expires_in"]

    for key in possible_keys:
        if key not in data:
            continue
        val = data[key]
        try:
            if key == "expires_in":
                return now + int(val)
            if key.endswith("_ms"):
                return int(val) // 1000  # ms → seconds
            expiry = int(val)
            # If the number is absurdly large (ms), convert
            if expiry > 10**12:
                expiry //= 1000
            return expiry
        except:
            continue

    return None


def main():
    args = parse_args()
    env = args.env.lower()
    path = Path.home() / ".config" / "trading_algo" / f"access_token_{env}.json"

    data = load_json(path)
    if not data:
        sys.exit(1)

    token = (
        data.get("access_token")
        or data.get("token")
        or data.get("accessToken")
    )

    if not token or not isinstance(token, str) or not token.strip():
        print(f"[validator] ❌ No valid token string found in {path}", flush=True)
        sys.exit(1)

    expiry_ts = extract_expiry(data)
    now = int(time.time())

    if expiry_ts is not None:
        if expiry_ts <= now + 60:  # treat <60s remaining as expired
            print(
                f"[validator] ❌ Token expired or near expiry "
                f"(expiry={expiry_ts}, now={now})",
                flush=True,
            )
            sys.exit(1)
        else:
            print(
                f"[validator] ✅ Token valid (expiry={expiry_ts}, now={now})",
                flush=True,
            )
            sys.exit(0)

    # No expiry present → assume valid (matches your current system)
    print("[validator] ⚠️ No expiry info. Treating token as VALID.", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
