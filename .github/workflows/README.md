# GitHub Workflows — Operational README

This document describes the two primary GitHub Actions workflows used by the `trading_algo` repository:
- `unified.yml` — main run workflow (cron + manual dispatch)
- `refresh.yml` — token refresh workflow (cron + callable)

This README is a non-executable operational specification intended for maintainers.

## Script entrypoints (expected paths)
- `trading_algo/run_saras.py` — run SARAS environment
- `trading_algo/run_vs.py` — run VS environment

Both scripts:
- accept `--config` (default: `examples/sample_config.yml`)
- accept `--command` (optional override)
- accept `--log-level`
- must return exit code `0` on success; non-zero on failure.

## High-level workflow behaviour

### unified.yml
- Trigger: canonical cron lines from original `unified.yml` (the SARAS/unified timings).
- Supports manual `workflow_dispatch` with `mode` input: `SARAS | VS | BOTH` (default: `BOTH`).
- For each environment to run:
  1. Preflight API ping using the token `ACCESS_TOKEN_{SARAS|VS}`. The ping uses the same `kite.profile()` call as in `auto_login.py`.
  2. If ping succeeds: continue to run the env-specific script.
  3. If ping fails: perform **one** inline refresh (headless login via `auto_login.py` logic) to obtain a token and `gh secret set` it using the PAT secret for that env. Re-run ping once.
  4. If ping still fails: send immediate failure email and skip that env.
  5. Run script: `python trading_algo/run_saras.py` or `python trading_algo/run_vs.py`.
  6. If the run script fails (non-zero exit), send immediate failure email. If `mode=BOTH`, SARAS runs before VS; SARAS failure does NOT prevent VS from running.

### refresh.yml
- Trigger: canonical cron(s) from original `refresh-token.yml`.
- Sequentially refreshes SARAS then VS tokens using the headless login flow (`auto_login.py`).
- On success, updates repo secret: `ACCESS_TOKEN_SARAS` / `ACCESS_TOKEN_VS` using respective PAT secrets.
- On failure, send immediate failure email. No automatic retries.

## Secrets (required)
- `ACCESS_TOKEN_SARAS`, `ACCESS_TOKEN_VS`
- `ACCESS_TOKEN_GH_PAT_SARAS`, `ACCESS_TOKEN_GH_PAT_VS` (PATs used to update secrets)
- Various environment secrets per env (e.g., `API_KEY_SARAS`, `API_SECRET_SARAS`, etc.)
- `SMTP_TOKEN_JSON_COMMON` — contains SMTP password only. Mailer uses host `smtp.gmail.com`, port `587`, from/username `sugamkuchhal@gmail.com`.

## Email notifications
- Recipient: `sugamkuchhal@gmail.com`
- Trigger: immediate per-failure (preflight/refresh/run)
- Subject pattern:
  `[trading_algo][FAILURE] <workflow-name> — <ENV> — <short reason>`
- Body contains timestamp, run link, small stderr excerpt, and suggested action.

## Preflight & refresh implementation note (where we borrow behavior)
- Use the same `kite.profile()` call and the `auto_login.py` headless flow for refresh and for the validation ping. This is already implemented in `auto_login.py` (it creates the kite client then calls `kite.profile()` in `main()`), so we will reuse that logic as the canonical check.

## Operational safeguards & assumptions
- Inline refresh will attempt at most one refresh per environment per workflow run (prevents infinite loops).
- Tokens are never uploaded as artifacts.
- Chrome/Chromium is installed only when a headless login is required.
- Runner script contract: `trading_algo/run_saras.py` and `trading_algo/run_vs.py` must exist at those paths, accept `--config` and `--command` optionally, and return 0 on success; non-zero on failure (workflow relies on exit codes).

## Local testing
- Run SARAS locally:

