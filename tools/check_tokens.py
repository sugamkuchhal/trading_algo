#!/usr/bin/env python3
"""
tools/check_tokens.py

Standalone script to:
  1) Run masked diagnostics on ACCESS_JSON_<ENV> and ACCESS_TOKEN_<ENV>
  2) Validate access tokens by calling kite.profile() for each env in order:
       SARAS then VS

Exit codes:
  0 - all good
  1 - missing env / invalid JSON / kite.profile() error
"""

import os
import sys
import json

try:
    from kiteconnect import KiteConnect
except Exception:
    # Fail fast with a helpful message — in CI you'll install kiteconnect in the workflow
    print("Missing dependency: kiteconnect. Install with `pip install kiteconnect`", file=sys.stderr)
    sys.exit(1)


def require_env(var):
    v = os.environ.get(var)
    if not v:
        print(f"Missing required env: {var}", file=sys.stderr)
        sys.exit(1)
    return v


def mask(s, keep=6):
    s = s.strip()
    if not s:
        return "(empty)"
    if len(s) <= keep:
        return s
    return s[:keep] + "..." + str(len(s)) + "chars"


def diagnostic(envs=("SARAS", "VS")):
    for env in envs:
        key = f"ACCESS_JSON_{env}"
        jstr = require_env(key)
        try:
            data = json.loads(jstr)
        except Exception as e:
            print(f"[{env}] ACCESS_JSON invalid JSON: {e}", file=sys.stderr)
            sys.exit(1)
        api_key = (data.get("api_key") or "").strip()
        token_env = f"ACCESS_TOKEN_{env}"
        token = os.environ.get(token_env, "").strip()

        print(f"[{env}] ACCESS_JSON present: yes")
        print(f"[{env}] api_key present: {'yes' if api_key else 'NO'}")
        print(f"[{env}] api_key (masked): {mask(api_key)}")
        print(f"[{env}] access_token present: {'yes' if token else 'NO'}")
        print(f"[{env}] access_token (masked/len): {mask(token)}")

        # detect obvious whitespace issues (rare if secrets set properly)
        if api_key and (api_key != api_key.strip()):
            print(f"[{env}] WARNING: api_key has leading/trailing whitespace", file=sys.stderr)
        if token and (token != token.strip()):
            print(f"[{env}] WARNING: access_token has leading/trailing whitespace", file=sys.stderr)

    print("Diagnostic checks completed.")


def parse_access_json(env_name):
    jstr = require_env(f"ACCESS_JSON_{env_name}")
    try:
        data = json.loads(jstr)
    except Exception as e:
        print(f"Invalid JSON in ACCESS_JSON_{env_name}: {e}", file=sys.stderr)
        sys.exit(1)
    api_key = data.get("api_key")
    if not api_key:
        print(f"ACCESS_JSON_{env_name} missing 'api_key'", file=sys.stderr)
        sys.exit(1)
    return data, api_key


def check_account(env_name):
    data, api_key = parse_access_json(env_name)
    access_token = require_env(f"ACCESS_TOKEN_{env_name}")

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    try:
        profile = kite.profile()
        print(f"[OK] {env_name} — user_id: {profile.get('user_id')}")
    except Exception as e:
        print(f"[FAILED] {env_name} — token invalid or API error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    envs = ("SARAS", "VS")
    diagnostic(envs)
    # Sequentially check SARAS then VS
    for e in envs:
        check_account(e)
    print("All token checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
