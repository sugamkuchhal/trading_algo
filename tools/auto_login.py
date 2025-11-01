#!/usr/bin/env python3
"""
tools/auto_login.py — unified headless Zerodha login for SARAS / VS.

Usage:
  python tools/auto_login.py --env saras
  python tools/auto_login.py --env vs

Behavior:
  - Launches headless Chrome (google-chrome-stable) for Zerodha login
  - Uses secrets from environment (API_KEY_*, API_SECRET_*, etc.)
  - Generates a new access_token via kiteconnect
  - Updates the GitHub secret ACCESS_TOKEN_<ENV> directly using the PAT
  - Does NOT write any local files
"""

import os
import sys
import time
import json
import pyotp
import logging
import subprocess
from urllib.parse import urlparse, parse_qs
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from kiteconnect import KiteConnect
from shutil import which

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)
log = logging.getLogger("auto_login")


def get_env_or_fail(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        log.error(f"❌ Required environment variable {name} is missing.")
        sys.exit(2)
    return val


def gh_update_secret(secret_name: str, secret_value: str, repo: str, gh_pat: str) -> None:
    """Use GitHub CLI to update a secret in the given repository."""
    env = os.environ.copy()
    env["GH_TOKEN"] = gh_pat
    cmd = [
        "gh",
        "secret",
        "set",
        secret_name,
        "--repo",
        repo,
        "--body",
        secret_value,
    ]
    log.info(f"🔐 Updating secret {secret_name} in {repo}")
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode == 0:
        log.info(f"✅ Successfully updated secret {secret_name}")
    else:
        log.error(f"❌ Failed to update secret {secret_name}: {result.stderr}")
        sys.exit(result.returncode)


def login_and_get_token(api_key, api_secret, user_id, password, totp_secret) -> str:
    """Perform headless login and return the access_token."""
    login_url = f"https://kite.zerodha.com/connect/login?api_key={api_key}&v=3"
    log.info(f"🌐 Opening {login_url}")

    chrome_path = which("google-chrome-stable") or which("google-chrome")
    driver_path = which("chromedriver")
    if not chrome_path or not driver_path:
        log.error("❌ google-chrome-stable or chromedriver not found in PATH.")
        sys.exit(3)

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,800")
    options.binary_location = chrome_path

    driver = webdriver.Chrome(service=Service(driver_path), options=options)
    wait = WebDriverWait(driver, 10)
    driver.get(login_url)

    try:
        wait.until(EC.presence_of_element_located((By.ID, "userid"))).send_keys(user_id)
        driver.find_element(By.ID, "password").send_keys(password)
        driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()

        wait.until(EC.presence_of_element_located((By.ID, "pin"))).send_keys(
            pyotp.TOTP(totp_secret).now()
        )
        driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
        time.sleep(3)

        current_url = driver.current_url
        log.info(f"🔄 Redirected to: {current_url}")
        parsed = urlparse(current_url)
        request_token = parse_qs(parsed.query).get("request_token", [None])[0]

        if not request_token:
            log.error("❌ Could not extract request_token from redirect URL.")
            sys.exit(4)

        log.info(f"✅ request_token acquired.")
    except Exception as e:
        log.error(f"❌ Login flow failed: {e}")
        sys.exit(5)
    finally:
        driver.quit()

    # Generate access token using KiteConnect
    kite = KiteConnect(api_key=api_key)
    session_data = kite.generate_session(request_token, api_secret=api_secret)
    access_token = session_data.get("access_token")
    log.info(f"✅ Access token obtained successfully.")
    return access_token


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True, choices=["saras", "vs"], help="Environment name")
    args = parser.parse_args()

    env = args.env.upper()
    repo = get_env_or_fail("REPO")

    api_key = get_env_or_fail(f"API_KEY_{env}")
    api_secret = get_env_or_fail(f"API_SECRET_{env}")
    user_id = get_env_or_fail(f"USER_ID_{env}")
    password = get_env_or_fail(f"PASSWORD_{env}")
    totp_secret = get_env_or_fail(f"TOTP_SECRET_{env}")

    gh_pat = get_env_or_fail(f"ACCESS_TOKEN_GH_PAT_{env}")
    secret_name = f"ACCESS_TOKEN_{env}"

    access_token = login_and_get_token(api_key, api_secret, user_id, password, totp_secret)
    gh_update_secret(secret_name, access_token, repo, gh_pat)


if __name__ == "__main__":
    main()
