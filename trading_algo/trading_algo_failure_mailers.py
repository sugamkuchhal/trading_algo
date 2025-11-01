import os
import smtplib
import textwrap
import json
from email.message import EmailMessage
from datetime import datetime
import sys

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "sugamkuchhal@gmail.com")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)

# New: support two secret formats:
# 1) SMTP_PASSWORD (plain password)
# 2) SMTP_TOKEN_JSON_COMMON (JSON blob containing the password/key)
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")

if not SMTP_PASSWORD:
    # Try parsing SMTP_TOKEN_JSON_COMMON if present
    token_json = os.environ.get("SMTP_TOKEN_JSON_COMMON")
    if token_json:
        try:
            data = json.loads(token_json)
            # try a few common key names (adjust to your JSON shape)
            SMTP_PASSWORD = (
                data.get("smtp_password")
                or data.get("password")
                or data.get("smtp", {}).get("password")
            )
        except Exception as e:
            # parsing failed — log and keep SMTP_PASSWORD None
            print("[WARN] Failed to parse SMTP_TOKEN_JSON_COMMON:", e, file=sys.stderr)
            SMTP_PASSWORD = None

def send_failure_email(workflow_name: str, env_name: str, stage: str, short_reason: str, run_url: str, log_excerpt: str = ""):
    """
    Send a failure email. Keep body short. If SMTP creds are not available,
    the function will log and return False (non-fatal).
    """
    if not SMTP_PASSWORD:
        # Do not raise here — log and return False so caller can continue.
        print("[WARN] SMTP credentials not found; skipping failure email", file=sys.stderr)
        return False

    subject = f"[trading_algo][FAILURE] {workflow_name} — {env_name} — {short_reason}"
    timestamp = datetime.utcnow().isoformat() + "Z"

    body = textwrap.dedent(f"""
    Timestamp (UTC): {timestamp}
    Workflow: {workflow_name}
    Environment: {env_name}
    Stage: {stage}
    Reason: {short_reason}

    Run URL: {run_url}

    Recent logs:
    {log_excerpt}

    Suggested actions:
    1. Check PATs listed in repo secrets.
    2. Inspect Actions run logs and the step that failed.
    3. If this is a token refresh failure, check the headless login flow on your local machine.

    This is an automated message from trading_algo.
    """)

    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = os.environ.get("ALERT_TO", "sugamkuchhal@gmail.com")
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.ehlo()
        s.starttls()
        s.ehlo()
        s.login(SMTP_USER, SMTP_PASSWORD)
        s.send_message(msg)
    return True
