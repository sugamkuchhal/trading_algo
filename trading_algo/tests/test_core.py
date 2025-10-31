from trading_algo.config import load_config
from trading_algo.core import signal_generation

def test_signal_generation(tmp_path):
    cfg_file = tmp_path / "cfg.yml"
    cfg_file.write_text("""
general:
  run_id: test
  log_level: INFO
trading:
  symbol: TEST
  timeframe: 1h
  max_positions: 1
""")
    cfg = load_config(str(cfg_file))
    sig = signal_generation(cfg)
    assert isinstance(sig, dict)
    assert sig.get("symbol") == "TEST"