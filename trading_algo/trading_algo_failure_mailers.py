#!/usr/bin/env python3
"""
trading_algo_failure_mailers.py

Simple SMTP mailer used by GitHub workflows to send failure emails.

Expected environment variables (set by the workflow):
- SMTP_PASSWORD      -> the SMTP password (value of your secret SMTP_TOKEN_JSON_COMMON)
- SMTP_FROM          -> email "from" (e.g. sugamkuchhal@gmail.com)
- SMTP_USER          -> SMTP username (e.g. sugamkuchhal@gmail.com)
- SMTP_HOST          -> smtp.gmail.com
- SMTP_PORT          -> 587

This module exposes send_failure_email(...) used by workflows.
"""

import os
import smtplib
import textwrap
from email.message import EmailMessage
from datetime import datetime

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "sugamkuchhal@gmail.com")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")  # required

def send_failure_email(workflow_name: str, env_name: str, stage: str, short_reason: str, run_url: str, log_excerpt: str = ""):
    """
    Send a failure email. Keep body short.
    """
    if not SMTP_PASSWORD:
        raise RuntimeError("SMTP_PASSWORD is not set in the environment")

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
