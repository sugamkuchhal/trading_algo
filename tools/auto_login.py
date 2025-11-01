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
    """
    Perform headless login and return the access_token.

    Robust hybrid version:
      - Uses CI-friendly google-chrome-stable binary
      - Includes anti-detection flags and incognito mode
      - Handles both "fresh login" and "session active" flows
      - Retries once on Timeout
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium import webdriver
    from kiteconnect import KiteConnect
    from shutil import which
    import time

    login_url = f"https://kite.zerodha.com/connect/login?api_key={api_key}&v=3"
    log.info(f"🌐 Opening {login_url}")

    chrome_path = which("google-chrome-stable") or which("google-chrome")
    driver_path = which("chromedriver")
    if not chrome_path or not driver_path:
        log.error("❌ google-chrome-stable or chromedriver not found in PATH.")
        sys.exit(3)

    # --- Chrome options (human-like headless mode)
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--incognito")
    options.add_argument("--window-size=1280,800")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.binary_location = chrome_path

    driver = webdriver.Chrome(service=Service(driver_path), options=options)
    wait = WebDriverWait(driver, 20)

    attempt = 0
    request_token = None

    while attempt < 2 and not request_token:
        attempt += 1
        try:
            driver.get(login_url)
            log.info(f"🔁 Attempt {attempt}: loading login page")

            # --- Detect which flow is served
            try:
                user_input = wait.until(EC.presence_of_element_located((By.ID, "userid")))
                user_input.clear()
                user_input.send_keys(user_id)
                log.info("🆕 Fresh login: entered USER ID")
            except TimeoutException:
                log.warning("⚠️ userid field not found — trying session-active flow")
            
            # --- Password field (appears on both flows)
            pwd_input = wait.until(EC.presence_of_element_located((By.ID, "password")))
            pwd_input.clear()
            pwd_input.send_keys(password)
            driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
            log.info("🔒 Entered password and clicked submit")

            # --- Wait for TOTP page
            try:
                pin_input = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.ID, "pin"))
                )
                pin_code = pyotp.TOTP(totp_secret).now()
                pin_input.send_keys(pin_code)
                log.info(f"📟 Entered TOTP ({pin_code})")
                driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
            except TimeoutException:
                log.error("❌ TOTP input not found.")
                raise

            time.sleep(3)
            current_url = driver.current_url
            parsed = urlparse(current_url)
            request_token = parse_qs(parsed.query).get("request_token", [None])[0]

            if request_token:
                log.info("✅ request_token acquired.")
            else:
                log.warning("⚠️ request_token not yet visible, retrying...")

        except TimeoutException:
            log.warning(f"⏳ Timeout during attempt {attempt}, retrying once more...")
            continue
        except Exception as e:
            log.error(f"❌ Unexpected error during login attempt {attempt}: {e}")
            continue

    driver.quit()

    if not request_token:
        log.error("❌ Could not obtain request_token after retries.")
        sys.exit(4)

    # --- Exchange for access token
    kite = KiteConnect(api_key=api_key)
    session_data = kite.generate_session(request_token, api_secret=api_secret)
    access_token = session_data.get("access_token")
    log.info("✅ Access token obtained successfully.")
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
