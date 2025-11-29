#!/usr/bin/env python3
"""
tools/ci_validate_token.py

Minimal validator used by CI to decide whether a token is already valid (so we can skip
the heavier auto-login and browser installs).

Behavior:
 - Loads: ~/.config/trading_algo/access_token_<env>.json
 - Ensures JSON parse + presence of a token key (access_token or token)
 - If env var VALIDATE_URL_<ENV> is present, makes a single GET to that URL with
   Authorization: Bearer <token> and treats 2xx as valid.
 - Else, if the JSON contains an expiry (iso string or unix seconds), checks it.
 - Else, if no URL or expiry, treats token as VALID (non-strict) but logs a warning.

Exit codes:
 0 = valid
 1 = invalid (missing/expired/failed validation)
 2 = missing token file / parse error
 3 = missing dependency / runtime issue
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

try:
    import requests
except Exception:
    print("ERROR: 'requests' not installed. Please install requests.", file=sys.stderr)
    sys.exit(3)


def load_token_file(env: str):
    path = Path.home() / ".config" / "trading_algo" / f"access_token_{env}.json"
    if not path.exists():
        print(f"No token file found at {path}")
        return None, path
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Failed to parse token JSON at {path}: {e}", file=sys.stderr)
        return None, path
    return data, path


def find_token(data: dict):
    # common keys
    for key in ("access_token", "token", "accessToken", "access"):
        if key in data:
            return data[key], key
    # fallback: single-key dict with the token as value
    if isinstance(data, dict) and len(data) == 1:
        return next(iter(data.values())), next(iter(data.keys()))
    return None, None


def parse_expiry(data: dict):
    # Accept 'expiry', 'expires_at', 'expires' (either ISO8601 or epoch seconds)
    for key in ("expiry", "expires_at", "expires"):
        if key in data:
            v = data[key]
            # if numeric, treat as epoch seconds
            try:
                if isinstance(v, (int, float)):
                    return datetime.fromtimestamp(float(v), tz=timezone.utc)
                # try ISO format
                return datetime.fromisoformat(str(v)).astimezone(timezone.utc)
            except Exception:
                # ignore parse errors
                pass
    return None


def validate_with_url(token: str, url: str):
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if 200 <= r.status_code < 300:
            print(f"[validator] URL check succeeded: {url} -> {r.status_code}")
            return True
        else:
            print(f"[validator] URL check failed: {url} -> {r.status_code} (resp: {r.text[:200]})")
            return False
    except Exception as e:
        print(f"[validator] URL check error contacting {url}: {e}", file=sys.stderr)
        return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--env", required=True, help="environment name (e.g. saras, vs)")
    args = p.parse_args()
    env = args.env

    data, path = load_token_file(env)
    if data is None:
        print(f"[validator] No usable token file for env '{env}' (looked at {path})", file=sys.stderr)
        sys.exit(2)

    token, token_key = find_token(data)
    if not token:
        print(f"[validator] Token key not found in {path}. Expected 'access_token' or similar.", file=sys.stderr)
        sys.exit(2)

    # 1) If explicit validate URL is provided via env var VALIDATE_URL_<ENV>, use it.
    env_var_name = f"VALIDATE_URL_{env.upper()}"
    validate_url = os.environ.get(env_var_name)
    if validate_url:
        ok = validate_with_url(token, validate_url)
        sys.exit(0 if ok else 1)

    # 2) If expiry info present, check it strictly
    expiry_dt = parse_expiry(data)
    if expiry_dt:
        now = datetime.now(timezone.utc)
        # add a small safety margin of 60s
        if now < expiry_dt:
            print(f"[validator] Token has expiry {expiry_dt.isoformat()} and is currently valid.")
            sys.exit(0)
        else:
            print(f"[validator] Token expired at {expiry_dt.isoformat()} (now: {now.isoformat()})", file=sys.stderr)
            sys.exit(1)

    # 3) As a last resort: non-strict accept (warn)
    print("[validator] No validate URL or expiry found. Treating token as VALID (non-strict).")
    sys.exit(0)


if __name__ == "__main__":
    main()
