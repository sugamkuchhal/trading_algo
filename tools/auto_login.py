#!/usr/bin/env python3
"""
tools/auto_login.py - universal auto-login for SARAS / VS

Single script that:
 - logs into Zerodha/Kite (handles External TOTP)
 - generates Kite access_token
 - saves the token BOTH locally (macOS Keychain or file) AND updates GitHub repo secret (if credentials provided)

Behavior (single code for both flows):
 - If running on macOS, token will be saved into macOS Keychain (preferred) and also to ~/.config/trading_algo/access_<env>.json (fallback).
 - If ACCESS_TOKEN_GH_PAT_<ENV> or GH_TOKEN is available the script will update the GitHub Actions secret ACCESS_TOKEN_<ENV> for the configured repo.
 - If GitHub update fails, the script will log the error but still keep the local copy.

Usage:
  python tools/auto_login.py --env saras
  python tools/auto_login.py --env vs

Env variables:
 - API_KEY_<ENV>, API_SECRET_<ENV>, USER_ID_<ENV>, PASSWORD_<ENV>, TOTP_SECRET_<ENV>
 - ACCESS_JSON_<ENV> (optional JSON blob with those keys)
 - ACCESS_TOKEN_GH_PAT_<ENV> (optional PAT used to update repo secret)
 - REPO (optional; default: sugamkuchhal/trading_algo)
"""

import os
import sys
import time
import json
import logging
import subprocess
from urllib.parse import urlparse, parse_qs
from shutil import which

# Third-party libs used at runtime.
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
except Exception:
    # We will error later with clearer message if missing
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("auto_login")


def load_env_config(env: str) -> dict:
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
    return {
        "api_key": os.environ.get(f"API_KEY_{env}"),
        "api_secret": os.environ.get(f"API_SECRET_{env}"),
        "user_id": os.environ.get(f"USER_ID_{env}"),
        "password": os.environ.get(f"PASSWORD_{env}"),
        "totp_secret": os.environ.get(f"TOTP_SECRET_{env}"),
    }


def gh_update_secret(secret_name: str, secret_value: str, repo: str, gh_pat_env_name: str) -> bool:
    """Attempt to update GitHub repo secret using gh CLI.
    Returns True on success, False on failure. Logs errors but does not exit.
    Uses ACCESS_TOKEN_GH_PAT_<ENV> or GH_TOKEN from environment if present.
    """
    gh_pat = os.environ.get(gh_pat_env_name) or os.environ.get("GH_TOKEN")
    cmd = ["gh", "secret", "set", secret_name, "--repo", repo, "--body", secret_value]
    env = os.environ.copy()
    if gh_pat:
        env["GH_TOKEN"] = gh_pat
    try:
        log.info("🔐 Updating secret %s in %s", secret_name, repo)
        r = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if r.returncode == 0:
            log.info("✅ Successfully updated secret %s", secret_name)
            return True
        else:
            log.error("❌ Failed to update secret %s: %s", secret_name, r.stderr.strip())
            return False
    except FileNotFoundError:
        log.error("❌ gh CLI not found in PATH. Install GitHub CLI or provide ACCESS_TOKEN_GH_PAT_<ENV> and GH_TOKEN env.")
        return False
    except Exception as e:
        log.error("❌ Exception while updating secret: %s", e)
        return False


def save_to_keychain(env: str, token: str) -> bool:
    """Save token to macOS Keychain using `security` CLI. Returns True on success.
    Uses service name trading_algo_ACCESS_TOKEN_<ENV>.
    """
    if sys.platform != "darwin":
        log.info("Skipping Keychain save: not running on macOS")
        return False
    service = f"trading_algo_ACCESS_TOKEN_{env}"
    try:
        # -U to update existing item if present
        cmd = [
            "security",
            "add-generic-password",
            "-a",
            os.environ.get("USER", "user"),
            "-s",
            service,
            "-w",
            token,
            "-U",
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            log.info("✅ Saved access token to macOS Keychain as %s", service)
            return True
        else:
            # Sometimes add-generic-password fails if item exists; try 'delete' then add.
            if "already exists" in r.stderr.lower():
                subprocess.run(["security", "delete-generic-password", "-s", service], capture_output=True)
                r2 = subprocess.run(cmd, capture_output=True, text=True)
                if r2.returncode == 0:
                    log.info("✅ Saved access token to macOS Keychain as %s", service)
                    return True
            log.error("❌ Keychain save failed: %s", r.stderr.strip())
            return False
    except FileNotFoundError:
        log.error("❌ security CLI not found; cannot save to macOS Keychain")
        return False
    except Exception as e:
        log.error("❌ Exception saving to Keychain: %s", e)
        return False


def save_to_local_file(env: str, token: str) -> bool:
    """Save token to ~/.config/trading_algo/access_<env>.json with 600 perms. Returns True on success."""
    cfg_dir = os.path.expanduser("~/.config/trading_algo")
    os.makedirs(cfg_dir, exist_ok=True)
    path = os.path.join(cfg_dir, f"access_{env.lower()}.json")
    try:
        with open(path, "w") as fh:
            json.dump({"access_token": token}, fh)
        os.chmod(path, 0o600)
        log.info("✅ Saved access token to %s", path)
        return True
    except Exception as e:
        log.error("❌ Failed to save token to file: %s", e)
        return False


def find_chrome_and_driver():
    chrome = which("google-chrome-stable") or which("google-chrome")
    driver = which("chromedriver")
    if not chrome and sys.platform == "darwin":
        mac_chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if os.path.exists(mac_chrome):
            chrome = mac_chrome
    return chrome, driver


def _find_totp_input(driver, wait, timeout=15):
    candidates = [
        (By.XPATH, "//label[contains(text(),'External TOTP')]/following::input[1]"),
        (By.CSS_SELECTOR, "input[inputmode='numeric']"),
        (By.CSS_SELECTOR, "input[type='tel']"),
        (By.CSS_SELECTOR, "input[type='number']"),
        (By.CSS_SELECTOR, "input[type='text'][maxlength='6']"),
        (By.XPATH, "//input[not(@type='hidden')][1]"),
    ]
    last_exc = None
    for by, sel in candidates:
        try:
            log.info("Trying locator: %s=%s", by, sel)
            el = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, sel)))
            if el.is_displayed() and el.is_enabled():
                try:
                    el = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((by, sel)))
                except Exception:
                    pass
                return el
        except Exception as e:
            last_exc = e
    raise last_exc if last_exc else TimeoutException("TOTP input not found")


def login_and_get_token(api_key, api_secret, user_id, password, totp_secret, headless=True) -> str:
    """Perform login, handle External TOTP, return Kite access_token."""
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

    use_webdriver_manager = (sys.platform == "darwin")
    chrome_path, system_driver_path = find_chrome_and_driver()

    driver_path = system_driver_path
    if use_webdriver_manager:
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            driver_path = ChromeDriverManager().install()
            log.info("Using webdriver-manager chromedriver: %s", driver_path)
        except Exception as e:
            log.warning("webdriver-manager failed: %s; falling back to system chromedriver", e)

    if not chrome_path or not driver_path:
        log.error("chrome or chromedriver not found (chrome=%s driver=%s)", chrome_path, driver_path)
        sys.exit(3)

    options = Options()
    if headless:
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
        options.add_argument("--start-maximized")
        options.add_argument("--window-size=1280,800")

    if chrome_path:
        options.binary_location = chrome_path

    service = Service(driver_path)
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

            try:
                user_input = wait.until(EC.presence_of_element_located((By.ID, "userid")))
                user_input.clear()
                user_input.send_keys(user_id)
                log.info("🆕 Entered USER ID")
            except TimeoutException:
                log.warning("⚠ userid not found (session-active or different markup).")

            pwd_input = wait.until(EC.presence_of_element_located((By.ID, "password")))
            pwd_input.clear()
            pwd_input.send_keys(password)
            try:
                submit_btn = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
                submit_btn.click()
            except Exception:
                try:
                    pwd_input.submit()
                except Exception:
                    driver.execute_script("""document.querySelector('button[type="submit"]').click();""")
            log.info("🔒 Entered password and submitted")

            for _ in range(6):
                try:
                    ready = driver.execute_script("return document.readyState")
                    if ready == "complete":
                        break
                except Exception:
                    pass
                time.sleep(0.5)

            try:
                totp_input = _find_totp_input(driver, wait, timeout=20)
            except Exception as e:
                log.error("❌ TOTP input not found: %s", e)
                raise

            pin_code = pyotp.TOTP(totp_secret).now()
            log.info("🔢 Generated TOTP (first 2 chars shown): %s", pin_code[:2] + "****")

            interacted = False
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", totp_input)
                time.sleep(0.3)
                totp_input.clear()
                totp_input.send_keys(pin_code)
                interacted = True
                log.info("ℹ Entered TOTP via send_keys")
            except Exception as e:
                log.warning("⚠ send_keys to TOTP input failed: %s", e)

            if not interacted:
                try:
                    log.info("ℹ Using JS fallback to set TOTP field and dispatch events")
                    set_val_js = """
                        var el = arguments[0];
                        el.focus();
                        el.value = arguments[1];
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    """
                    driver.execute_script(set_val_js, totp_input, pin_code)
                    interacted = True
                except Exception as e:
                    log.error("❌ JS fallback to set TOTP failed: %s", e)
                    raise

            clicked = False
            try:
                cont = None
                try:
                    cont = WebDriverWait(driver, 6).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[normalize-space() = 'Continue']"))
                    )
                except Exception:
                    try:
                        cont = WebDriverWait(driver, 6).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
                        )
                    except Exception:
                        cont = None

                if cont:
                    try:
                        cont.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", cont)
                    clicked = True
                    log.info("✅ Clicked Continue/Submit")
                else:
                    log.warning("⚠ Continue/Submit button not found; attempting form submit via JS")
                    driver.execute_script("var b = document.querySelector('button[type=\\"submit\\"]'); if(b){ b.click(); } else { var f = document.querySelector('form'); if(f){ f.submit(); }}")
                    clicked = True
            except Exception as e:
                log.warning("⚠ Continue click fallback failed: %s", e)

            log.info("📟 Entered TOTP / submitted, waiting for redirect...")
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
            continue
        except Exception as e:
            log.error("❌ Unexpected error on attempt %d: %s", attempt, e)
            try:
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
    parser.add_argument("--headless", action="store_true", default=False)
    args = parser.parse_args()

    env = args.env.upper()
    repo = os.environ.get("REPO", "sugamkuchhal/trading_algo")

    cfg = load_env_config(env)
    api_key = cfg.get("api_key")
    api_secret = cfg.get("api_secret")
    user_id = cfg.get("user_id")
    password = cfg.get("password")
    totp_secret = cfg.get("totp_secret")

    missing = [k for k, v in (("api_key", api_key), ("api_secret", api_secret), ("user_id", user_id), ("password", password), ("totp_secret", totp_secret)) if not v]
    if missing:
        log.error("Missing required credentials for %s: %s", env, missing)
        sys.exit(2)

    headless_env = os.environ.get("CI", "").lower() in ("true", "1") or os.environ.get("HEADLESS", "").lower() in ("true", "1")
    headless = args.headless or headless_env

    gh_pat_env_name = f"ACCESS_TOKEN_GH_PAT_{env}"

    access_token = login_and_get_token(api_key, api_secret, user_id, password, totp_secret, headless=headless)

    # Save locally (mac Keychain preferred, plus file backup)
    keychain_ok = save_to_keychain(env, access_token)
    file_ok = save_to_local_file(env, access_token)

    # Update GitHub secret if possible (best effort)
    gh_ok = gh_update_secret(f"ACCESS_TOKEN_{env}", access_token, repo, gh_pat_env_name)

    if not (keychain_ok or file_ok):
        log.warning("⚠ Token was not saved locally")
    if not gh_ok:
        log.warning("⚠ Token was not updated in GitHub secrets")

    if keychain_ok or file_ok or gh_ok:
        log.info("All storage attempts finished.")
    else:
        log.error("No storage succeeded; please check logs and environment variables.")


if __name__ == "__main__":
    main()
