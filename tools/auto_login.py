#!/usr/bin/env python3
"""
tools/auto_login.py - universal auto-login for SARAS / VS

Usage:
  python tools/auto_login.py --env saras
  python tools/auto_login.py --env vs

Notes:
- Reads consolidated JSON secret ACCESS_JSON_<ENV> if present, otherwise falls back to API_KEY_*/API_SECRET_* etc.
- Updates GitHub secret ACCESS_TOKEN_<ENV> via `gh secret set` using ACCESS_TOKEN_GH_PAT_<ENV>.
- Works on macOS (local) and in GitHub Actions (CI).
"""

import os
import sys
import time
import json
import logging
import subprocess
from urllib.parse import urlparse, parse_qs
from shutil import which

# optional imports; will error early if selenium/kiteconnect missing
try:
    import pyotp
    from kiteconnect import KiteConnect
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException
except Exception as e:
    # Defer import errors until runtime for clearer logs
    pass

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("auto_login")


def load_env_config(env: str) -> dict:
    """
    Load consolidated JSON secret ACCESS_JSON_<ENV> if present,
    otherwise fall back to individual env vars.

    Returns dict with keys: api_key, api_secret, user_id, password, totp_secret
    """
    json_name = f"ACCESS_JSON_{env}"
    j = os.environ.get(json_name)
    if j:
        try:
            cfg = json.loads(j)
            return {
                "api_key": cfg.get("api_key") or os.environ.get(f"API_KEY_{env}"),
                "api_secret": cfg.get("api_secret") or os.environ.get(f"API_SECRET_{env}"),
                "user_id": cfg.get("user_id") or os.environ.get(f"USER_ID_{env}"),
                "password": cfg.get("password") or os.environ.get(f"PASSWORD_{env}"),
                "totp_secret": cfg.get("totp_secret") or os.environ.get(f"TOTP_SECRET_{env}"),
            }
        except Exception as e:
            log.error("Failed to parse %s: %s", json_name, e)
            sys.exit(2)
    # fallback to individual env vars
    return {
        "api_key": os.environ.get(f"API_KEY_{env}"),
        "api_secret": os.environ.get(f"API_SECRET_{env}"),
        "user_id": os.environ.get(f"USER_ID_{env}"),
        "password": os.environ.get(f"PASSWORD_{env}"),
        "totp_secret": os.environ.get(f"TOTP_SECRET_{env}"),
    }


def gh_update_secret(secret_name: str, secret_value: str, repo: str, gh_pat: str) -> None:
    """Use GitHub CLI to update a secret in the given repository. Exits on failure."""
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
    log.info("🔐 Updating secret %s in %s", secret_name, repo)
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode == 0:
        log.info("✅ Successfully updated secret %s", secret_name)
    else:
        log.error("❌ Failed to update secret %s: %s", secret_name, result.stderr.strip())
        sys.exit(result.returncode)


def find_chrome_and_driver():
    """
    Return (chrome_binary_path, chromedriver_path).
    - On CI: prefer google-chrome-stable and system chromedriver (should be installed by workflow).
    - On mac: try system Chrome path or chrome in PATH; if chromedriver not found, suggest webdriver-manager.
    """
    # CI preferred names
    chrome = which("google-chrome-stable") or which("google-chrome")
    driver = which("chromedriver")

    # macOS common path
    if not chrome and sys.platform == "darwin":
        mac_chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if os.path.exists(mac_chrome):
            chrome = mac_chrome

    return chrome, driver


def login_and_get_token(api_key, api_secret, user_id, password, totp_secret, headless=True) -> str:
    """
    Robust login helper with macOS-friendly behavior:
    - Uses webdriver-manager locally to ensure driver compatibility.
    - Uses minimal Chrome options for non-headless (visible) runs.
    - Keeps more anti-detection flags for headless/CI runs.
    """
    try:
        import pyotp
        from kiteconnect import KiteConnect
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException
    except Exception as e:
        log.error("Missing dependencies: %s", e)
        log.error("Install: pip install kiteconnect selenium pyotp webdriver-manager")
        sys.exit(6)

    # On mac (local) prefer webdriver-manager to avoid driver mismatch issues.
    use_webdriver_manager = (sys.platform == "darwin")

    chrome_path, system_driver_path = find_chrome_and_driver()

    # If using webdriver-manager, fetch a matching driver binary and point to it
    driver_path = system_driver_path
    if use_webdriver_manager:
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            driver_exe = ChromeDriverManager().install()
            driver_path = driver_exe
            log.info("Using webdriver-manager chromedriver: %s", driver_path)
        except Exception as e:
            log.warning("webdriver-manager failed: %s; falling back to system chromedriver", e)

    if not chrome_path or not driver_path:
        log.error("chrome or chromedriver not found (chrome=%s driver=%s)", chrome_path, driver_path)
        sys.exit(3)

    options = Options()
    # If headless (CI): enable anti-detection and robust flags
    if headless:
        # prefer new headless where available
        options.add_argument("--headless=new")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument("--disable-extensions")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1280,800")
    else:
        # Visible browser (local debug): keep options minimal to avoid macOS UI prompts/crashes
        options.add_argument("--start-maximized")
        options.add_argument("--window-size=1280,800")
        # do NOT add incognito/automation-disable options that sometimes cause mac crashes

    # Use explicit binary if found
    if chrome_path:
        options.binary_location = chrome_path

    service = Service(driver_path)
    # Enable verbose logging from chromedriver when debugging
    service.log_path = os.environ.get("CHROMEDRIVER_LOG", "/tmp/chromedriver.log")

    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 20)

    login_url = f"https://kite.zerodha.com/connect/login?api_key={api_key}&v=3"
    log.info("🌐 Opening %s", login_url)

    request_token = None
    attempt = 0
    max_attempts = 2

    while attempt < max_attempts and not request_token:
        attempt += 1
        try:
            driver.get(login_url)
            log.info("🔁 Attempt %d: loading login page", attempt)

            # Try fresh login -> userid
            try:
                user_input = wait.until(EC.presence_of_element_located((By.ID, "userid")))
                user_input.clear()
                user_input.send_keys(user_id)
                log.info("🆕 Entered USER ID")
            except TimeoutException:
                log.warning("⚠ userid not found (session-active or different markup).")

            # password field (should be present)
            pwd_input = wait.until(EC.presence_of_element_located((By.ID, "password")))
            pwd_input.clear()
            pwd_input.send_keys(password)
            driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
            log.info("🔒 Entered password and submitted")

            # --- Wait for page fully loaded (helps with racey SPAs)
            for _ in range(6):
                try:
                    ready = driver.execute_script("return document.readyState")
                    if ready == "complete":
                        break
                except Exception:
                    pass
                time.sleep(0.5)
            
            # pin (TOTP) page — robust approach
            pin_input = None
            try:
                pin_input = WebDriverWait(driver, 20).until(
                    EC.element_to_be_clickable((By.ID, "pin"))
                )
            except TimeoutException:
                log.warning("⚠ pin element not clickable by timeout; trying presence fallback")
                try:
                    pin_input = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.ID, "pin"))
                    )
                except TimeoutException:
                    log.error("❌ TOTP input not found (presence fallback).")
                    raise
            
            pin_code = pyotp.TOTP(totp_secret).now()
            
            # Try normal interaction first
            interacted = False
            try:
                # ensure visible
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", pin_input)
                pin_input.clear()
                pin_input.send_keys(pin_code)
                interacted = True
            except Exception as e:
                log.warning("⚠ pin send_keys failed: %s", e)
            
            # If send_keys didn't work, set value via JS & dispatch events
            if not interacted:
                try:
                    log.info("ℹ Using JS to set TOTP value (fallback)")
                    set_val_js = """
                        var el = document.getElementById('pin');
                        if (!el) { throw 'pin element missing'; }
                        el.focus();
                        el.value = arguments[0];
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    """
                    driver.execute_script(set_val_js, pin_code)
                    interacted = True
                except Exception as e:
                    log.error("❌ JS fallback to set pin failed: %s", e)
                    raise
            
            # Submit — try normal click, fallback to JS click
            try:
                btn = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[type="submit"]')))
                try:
                    btn.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", btn)
            except TimeoutException:
                # As last resort, fire form submit via JS
                log.warning("⚠ submit button not clickable — trying form submit via JS")
                try:
                    driver.execute_script("""
                        var b = document.querySelector('button[type="submit"]');
                        if (b) { b.click(); } else {
                            var f = document.querySelector('form');
                            if (f) { f.submit(); }
                        }
                    """)
                except Exception as e:
                    log.error("❌ Could not submit form: %s", e)
                    raise
            
            log.info("📟 Entered TOTP / submitted")
            
            time.sleep(3)
            current_url = driver.current_url
            log.info("🔄 Redirected to %s", current_url)
            parsed = urlparse(current_url)
            request_token = parse_qs(parsed.query).get("request_token", [None])[0]

            if request_token:
                log.info("✅ request_token acquired")
            else:
                log.warning("⚠ request_token not found yet; will retry if attempts remain")

        except TimeoutException as te:
            log.warning("⏳ Timeout on attempt %d: %s", attempt, te)
            # try again
            continue
        except Exception as e:
            # If the browser died unexpectedly, capture chromedriver log (if any) to help debugging
            log.error("❌ Unexpected error on attempt %d: %s", attempt, e)
            try:
                log.info("Collecting chromedriver debug log (if present):")
                logpath = service.log_path
                if os.path.exists(logpath):
                    with open(logpath, "r", errors="ignore") as fh:
                        tail = fh.read()[-4000:]
                        log.info("=== chromedriver tail ===\n%s\n=== end chromedriver tail ===", tail)
            except Exception:
                pass
            continue
        finally:
            pass

    try:
        driver.quit()
    except Exception:
        pass

    if not request_token:
        log.error("❌ Could not obtain request_token after %d attempts", max_attempts)
        sys.exit(4)

    kite = KiteConnect(api_key=api_key)
    session_data = kite.generate_session(request_token, api_secret=api_secret)
    access_token = session_data.get("access_token")
    if not access_token:
        log.error("❌ KiteConnect did not return access_token: %s", session_data)
        sys.exit(7)
    log.info("✅ Access token obtained")
    return access_token


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True, choices=["saras", "vs"])
    parser.add_argument("--headless", action="store_true", default=False, help="force headless")
    args = parser.parse_args()

    env = args.env.upper()
    repo = os.environ.get("REPO", "sugamkuchhal/trading_algo")

    # load config (JSON first, fallback to individual env vars)
    cfg = load_env_config(env)
    api_key = cfg.get("api_key") or os.environ.get(f"API_KEY_{env}")
    api_secret = cfg.get("api_secret")
    user_id = cfg.get("user_id")
    password = cfg.get("password")
    totp_secret = cfg.get("totp_secret")

    # validate
    missing = [k for k, v in (("api_key", api_key), ("api_secret", api_secret),
                              ("user_id", user_id), ("password", password),
                              ("totp_secret", totp_secret)) if not v]
    if missing:
        log.error("Missing required credentials for %s: %s", env, missing)
        sys.exit(2)

    # select headless behaviour:
    # - If running in CI (CI=true) or user passed --headless, run headless.
    headless_env = os.environ.get("CI", "").lower() in ("true", "1") or os.environ.get("HEADLESS", "").lower() in ("true", "1")
    headless = args.headless or headless_env

    gh_pat = os.environ.get(f"ACCESS_TOKEN_GH_PAT_{env}")
    if not gh_pat:
        log.error("Missing PAT: ACCESS_TOKEN_GH_PAT_%s", env)
        sys.exit(2)

    secret_name = f"ACCESS_TOKEN_{env}"

    access_token = login_and_get_token(api_key, api_secret, user_id, password, totp_secret, headless=headless)

    # update GitHub secret with the PAT provided
    gh_update_secret(secret_name, access_token, repo, gh_pat)
    log.info("All done for %s", env)


if __name__ == "__main__":
    main()
