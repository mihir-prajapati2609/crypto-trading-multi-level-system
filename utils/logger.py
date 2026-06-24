import logging
import sys
import json
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler

TRADE_LEVEL = 25
logging.addLevelName(TRADE_LEVEL, "TRADE")

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_data"):
            log_obj.update(record.extra_data)
        return json.dumps(log_obj)

def setup_logging(log_dir: Path, level: int = logging.INFO):
    """Configures structured logging."""
    log_dir.mkdir(parents=True, exist_ok=True)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Ensure stdout handles emojis correctly
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        
    # Console handler (human readable)
    console_handler = logging.StreamHandler(sys.stdout)
    console_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)
    
    # File handler (JSON)
    def add_file_handler(filename, log_level):
        handler = RotatingFileHandler(log_dir / filename, maxBytes=50*1024*1024, backupCount=7, encoding='utf-8')
        handler.setFormatter(JsonFormatter())
        handler.setLevel(log_level)
        root_logger.addHandler(handler)
        
    add_file_handler("debug.log", logging.DEBUG)
    add_file_handler("errors.log", logging.ERROR)
    
    # Trade logger
    trade_handler = RotatingFileHandler(log_dir / "trades.log", maxBytes=50*1024*1024, backupCount=7, encoding='utf-8')
    trade_handler.setFormatter(JsonFormatter())
    trade_handler.setLevel(TRADE_LEVEL)
    
    class TradeFilter(logging.Filter):
        def filter(self, record):
            return record.levelno == TRADE_LEVEL
            
    trade_handler.addFilter(TradeFilter())
    root_logger.addHandler(trade_handler)
    
    # Add trade method to logger
    def trade(self, message, *args, **kws):
        if self.isEnabledFor(TRADE_LEVEL):
            self._log(TRADE_LEVEL, message, args, **kws)
            
    logging.Logger.trade = trade
