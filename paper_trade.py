import os

# Force paper trading mode
os.environ["TRADING_MODE"] = "paper"

from main import ArbitrageSystem, setup_logging, get_settings
import asyncio
import signal
import sys

if __name__ == "__main__":
    setup_logging(get_settings().log_dir)
    sys_obj = ArbitrageSystem()
    
    def handle_sigint(sig, frame):
        asyncio.create_task(sys_obj.stop())
        
    signal.signal(signal.SIGINT, handle_sigint)
    
    try:
        asyncio.run(sys_obj.start())
    except KeyboardInterrupt:
        pass
