import argparse
import logging
import sys
from .config import load_config
from .core import signal_generation, execute_signals

def setup_logging(level: str):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

def main(argv=None):
    parser = argparse.ArgumentParser(description="Run trading algo")
    parser.add_argument("--config", "-c", default="examples/sample_config.yml")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    setup_logging(cfg.log_level)
    signals = signal_generation(cfg)
    success = execute_signals(signals)
    return 0 if success else 1

if __name__ == "__main__":
    raise SystemExit(main())