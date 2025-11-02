# trading_algo

Repository for automated trading algorithm experiments and cron-run scheduling.

## Structure
- `trading_algo/` : main package
- `.github/workflows/cron_run.yml` : GitHub Actions cron workflow
- `examples/sample_config.yml` : example run configuration
- `tests/` : unit tests

## Quickstart (local)
1. Create a virtualenv:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Edit `examples/sample_config.yml`.
3. Run:
   ```bash
   python -m trading_algo.runner --config examples/sample_config.yml
   ```

## CI / Cron
A GitHub Actions workflow triggers a scheduled run; see `.github/workflows/cron_run.yml`.

## License
MIT