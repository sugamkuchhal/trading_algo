#!/usr/bin/env python3
import sys
import argparse
p = argparse.ArgumentParser()
p.add_argument('--config', default='examples/sample_config.yml')
p.add_argument('--command', default='')
args = p.parse_args()
print("run_vs placeholder; config=", args.config, "command=", args.command)
# return success (0) for now
sys.exit(0)
