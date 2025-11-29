#!/usr/bin/env python3
"""
set_field_false.py

Usage:
  python set_field_false.py --env SARAS [--lookup sheet_lookup.json] [--dry-run]

Behavior:
  - FILE_TYPE is a constant inside this file (change it here when needed).
  - Reads sheet_lookup.json at repo root by default (override with --lookup).
  - Looks up sheet_lookup[ENV][FILE_TYPE]["spreadsheet_ids"] and updates the single spreadsheet id found.
  - Uses credentials at ~/.config/trading_algo/<env_lower>.json (e.g. ~/.config/trading_algo/saras.json)
  - Updates SHEET_NAME!CELL to the literal string "FALSE".
  - Exits non-zero on missing mapping or other fatal errors.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# --- Edit these constants if you want to change file_type / sheet/cell ---
FILE_TYPE = "PORTFOLIO"            # <<-- constant inside the script (no CLI)
SHEET_NAME = "ALL_OLD_GTTs"        # <<-- constant inside the script (no CLI)
CELL = "R1"                        # <<-- constant inside the script (no CLI)
# -----------------------------------------------------------------------

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def load_lookup(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Lookup JSON not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)

def find_spreadsheet_id(lookup: dict, env: str, file_type: str):
    # We support case-insensitive env/file_type matching by normalizing keys
    normalized = {k.upper(): v for k, v in lookup.items()}
    env_key = env.upper()
    if env_key not in normalized:
        raise KeyError(f"Environment '{env}' not found in lookup JSON.")
    env_block = normalized[env_key]

    # normalize file_type keys
    normalized_ft = {k.upper(): v for k, v in env_block.items()}
    ft_key = file_type.upper()
    if ft_key not in normalized_ft:
        raise KeyError(f"file_type '{file_type}' not found under env '{env}'.")
    ft_block = normalized_ft[ft_key]

    sids = ft_block.get("spreadsheet_ids")
    if not sids or not isinstance(sids, list):
        raise KeyError(f"No 'spreadsheet_ids' list for env '{env}' file_type '{file_type}'.")
    if len(sids) != 1:
        # Per your rule, we expect exactly one spreadsheet id.
        raise ValueError(f"'spreadsheet_ids' must contain exactly one ID. Found {len(sids)}.")
    return sids[0]

def main():
    parser = argparse.ArgumentParser(description="Set a cell to FALSE for a given env+file_type (file_type is in-script).")
    parser.add_argument("--env", required=True, help="Environment name e.g. SARAS or VS")
    parser.add_argument("--lookup", default="sheet_lookup.json", help="Path to sheet lookup JSON (default: sheet_lookup.json)")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without calling Google Sheets API")
    args = parser.parse_args()

    env = args.env
    lookup_path = Path(args.lookup)

    try:
        lookup = load_lookup(lookup_path)
    except Exception as exc:
        eprint("Failed to load lookup JSON:", exc)
        sys.exit(2)

    try:
        spreadsheet_id = find_spreadsheet_id(lookup, env, FILE_TYPE)
    except Exception as exc:
        eprint("Lookup resolution error:", exc)
        sys.exit(3)

    # creds path per Option A
    env_lower = env.lower()
    creds_path = Path(os.path.expanduser(f"~/.config/trading_algo/creds_{env_lower}.json"))
    if not creds_path.exists():
        eprint(f"Credentials file not found for env '{env}': {creds_path}")
        eprint("Place the Google service account JSON at that location or set up CI to create it.")
        sys.exit(4)

    # Compose range
    range_name = f"{SHEET_NAME}!{CELL}"
    body_values = [["FALSE"]]

    print(f"ENV    : {env}")
    print(f"FILE_TYPE: {FILE_TYPE}")
    print(f"Spreadsheet ID: {spreadsheet_id}")
    print(f"Range to update: {range_name}")
    print(f"Creds file: {creds_path}")
    if args.dry_run:
        print("Dry-run mode enabled. No API calls will be made.")
        sys.exit(0)

    # Real API interaction
    try:
        # Import here to fail gracefully in dry environments
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
        service = build("sheets", "v4", credentials=creds)

        result = service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            body={"values": body_values}
        ).execute()

        updated = result.get("updatedCells") or result.get("updatedRange") or result
        print("Update result:", updated)
        print("SUCCESS: Updated cell to FALSE.")
        sys.exit(0)

    except Exception as exc:
        eprint("Google Sheets update failed:", exc)
        sys.exit(5)

if __name__ == "__main__":
    main()
