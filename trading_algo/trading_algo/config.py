from pathlib import Path
import yaml
from pydantic import BaseModel

class TradingConfig(BaseModel):
    run_id: str
    log_level: str
    symbol: str
    timeframe: str
    max_positions: int

def load_config(path: str) -> TradingConfig:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    raw = yaml.safe_load(p.read_text())
    g = raw.get("general", {})
    t = raw.get("trading", {})
    merged = {
        "run_id": g.get("run_id", "run-unknown"),
        "log_level": g.get("log_level", "INFO"),
        "symbol": t.get("symbol"),
        "timeframe": t.get("timeframe"),
        "max_positions": t.get("max_positions", 1),
    }
    return TradingConfig(**merged)