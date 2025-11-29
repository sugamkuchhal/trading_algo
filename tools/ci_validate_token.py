#!/usr/bin/env python3
# tools/ci_validate_token.py
# Validates a preloaded access token file for the given env by calling KiteConnect.profile().
# Exits 0 if valid, non-zero otherwise.

import os
import sys
import json


def get_api_key_for_env(env_up: str):
    # Try ACCESS_JSON_<ENV> first (workflow may set it)
    env_json_name = f"ACCESS_JSON_{env_up}"
    j = os.environ.get(env_json_name)
    if j:
        try:
            cfg = json.loads(j)
            api_key = cfg.get("api_key")
            if api_key:
                return api_key
        except Exception:
            pass

    # Fallback: direct env variable API_KEY_<ENV>
    api_key = os.environ.get(f"API_KEY_{env_up}")
    if api_key:
        return api_key

    # No usable API key found
    return None


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True, choices=["saras", "vs"])
    args = parser.parse_args()

    env = args.env.lower()
    env_up = env.upper()

    # Token file path
    cfg_path = os.path.expanduser(f"~/.config/trading_algo/access_token_{env}.json")
    if not os.path.exists(cfg_path):
        print(f"No token file at {cfg_path}", file=sys.stderr)
        sys.exit(1)

    # Read token
    try:
        with open(cfg_path) as fh:
            data = json.load(fh)
        token = data.get("access_token")
        if not token:
            print("No access_token in file", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print("Failed reading token file:", e, file=sys.stderr)
        sys.exit(1)

    # Read API key
    api_key = get_api_key_for_env(env_up)
    if not api_key:
        print("No api_key available to validate token; marking invalid", file=sys.stderr)
        sys.exit(1)

    # Import kiteconnect
    try:
        from kiteconnect import KiteConnect
    except Exception as e:
        print("kiteconnect not available:", e, file=sys.stderr)
        sys.exit(1)

    # Validate token
    try:
        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(token)
        kite.profile()   # authenticated call
        print("VALID")
        sys.exit(0)
    except Exception as e:
        print("Token validation failed:", e, file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
