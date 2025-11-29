#!/usr/bin/env python3
"""
tools/ci_validate_token.py

Exit codes:
  0 -> token considered VALID
  1 -> token considered INVALID (CI should install chrome + selenium and run full login)

Behavior:
  - Looks for ~/.config/trading_algo/access_token_<env>.json
  - Checks presence of token string.
  - Attempts to parse common expiry fields; if present must be > now + 60s.
  - If expiry is missing -> non-strict mode -> treat as VALID.
"""

import argparse
import json
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
        raw = path.read_text()
        # some workflows echo strings with surrounding quotes; try to clean common wrappers
        raw = raw.strip()
        # if the secret is a bare token string rather than JSON, wrap it:
        if raw and not (raw.startswith("{") and raw.endswith("}")):
            # attempt to decode as plain token
            return {"access_token": raw.strip('"').strip("'")}
        return json.loads(raw)
    except Exception as e:
        print(f"[validator] ❌ Failed to parse token file: {e}", flush=True)
        return None


def extract_expiry(data: dict):
    now = int(time.time())
    possible_keys = [
        "expiry",
        "expires_at",
        "expiry_ts",
        "expires_at_ms",
        "expires_in",
        "expires",
        "exp",
    ]
    for key in possible_keys:
        if key not in data:
            continue
        val = data.get(key)
        try:
            if val is None:
                continue
            if key == "expires_in":
                return now + int(val)
            if key.endswith("_ms"):
                return int(val) // 1000
            expiry = int(val)
            # if expiry looks like ms timestamp, convert
            if expiry > 10**12:
                expiry //= 1000
            return expiry
        except Exception:
            continue
    return None


def main():
    args = parse_args()
    env = args.env.lower()
    path = Path.home() / ".config" / "trading_algo" / f"access_token_{env}.json"

    data = load_json(path)
    if not data:
        print("[validator] ❌ No token data loaded.", flush=True)
        sys.exit(1)

    token = (
        data.get("access_token")
        or data.get("token")
        or data.get("accessToken")
        or data.get("token_value")
        or data.get("value")
    )

    if not token or not isinstance(token, str) or not token.strip():
        print("[validator] ❌ No valid token string found.", flush=True)
        sys.exit(1)

    expiry_ts = extract_expiry(data)
    now = int(time.time())

    if expiry_ts is not None:
        if expiry_ts <= now + 60:
            print(f"[validator] ❌ Token expired or near-expiry (expiry={expiry_ts}, now={now}).", flush=True)
            sys.exit(1)
        else:
            print(f"[validator] ✅ Token valid (expiry={expiry_ts}, now={now}).", flush=True)
            sys.exit(0)

    # No expiry present -> non-strict mode -> treat as valid
    print("[validator] ⚠️ No expiry info present. Treating token as VALID (non-strict).", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
